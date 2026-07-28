from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import tasks, organizations, users
from app.auth import get_current_user, require_internal
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.ids import new_id, now, as_aware, to_out, to_out_many

router = APIRouter(
    prefix="/api/tasks",
    tags=["tasks"],
    dependencies=[Depends(get_current_user), Depends(require_internal)],
)


@router.get("/team/roster")
async def team_roster():
    """Roster + workload, for Admin/Ops Manager view. Registered before
    '/{task_id}'-shaped routes (there are none here besides PATCH, so no
    ordering hazard, but kept explicit for clarity)."""
    all_users = await users.find({"role": {"$regex": "^roskyro_"}}).sort([("role", 1), ("name", 1)]).to_list(None)

    # One query for every internal user's tasks, then tally per-user in
    # Python -- not 3 count_documents() calls PER user (a 1+3*N query
    # pattern that scaled with headcount), same batch-fetch fix used
    # elsewhere in this file's list_tasks (org/assigned-user $in lookups).
    user_ids = [u["_id"] for u in all_users]
    all_tasks = await tasks.find({"assigned_to": {"$in": user_ids}}).to_list(None) if user_ids else []
    right_now = now()
    counts_by_user: dict = {}
    for t in all_tasks:
        c = counts_by_user.setdefault(t["assigned_to"], {"open": 0, "overdue": 0, "completed": 0})
        if t["status"] == "done":
            c["completed"] += 1
        else:
            c["open"] += 1
            if t.get("sla_due_at") and as_aware(t["sla_due_at"]) < right_now:
                c["overdue"] += 1

    roster = []
    for u in all_users:
        c = counts_by_user.get(u["_id"], {"open": 0, "overdue": 0, "completed": 0})
        roster.append({
            "id": u["_id"], "name": u.get("name"), "email": u.get("email"),
            "role": u.get("role"), "status": u.get("status"),
            "open_tasks": c["open"], "overdue_tasks": c["overdue"], "completed_tasks": c["completed"],
        })
    return {"roster": roster}


@router.get("/summary")
async def tasks_summary(role: str | None = None):
    # Fixed: same unbounded-fetch-then-tally-in-Python pattern as
    # list_tasks above -- this pulled every matching task (again, no
    # collection-level bound) just to count them by status. A per-status
    # count + overdue-count is exactly what MongoDB's $group/$sum are for;
    # now Mongo does the counting and only 1 row per distinct status
    # (a handful) ever crosses back into Python.
    filt = {"assigned_role": role} if role else {}
    # Naive, not aware -- see as_aware()'s docstring in app/utils/ids.py:
    # Mongo (and mongomock) round-trip stored datetimes as naive even
    # though they were inserted timezone-aware, and mongomock's aggregation
    # evaluator compares Python datetime objects directly (unlike a real
    # server, which compares BSON dates, not Python objects), so an aware
    # literal here raises "can't compare offset-naive and offset-aware
    # datetimes" the moment $lt actually evaluates it against a stored
    # sla_due_at.
    right_now = now().replace(tzinfo=None)
    grouped = await tasks.aggregate([
        {"$match": filt},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "overdue_count": {"$sum": {"$cond": [
                {"$and": [
                    {"$ne": ["$status", "done"]},
                    {"$ne": ["$sla_due_at", None]},
                    {"$lt": ["$sla_due_at", right_now]},
                ]},
                1, 0,
            ]}},
        }},
    ]).to_list(None)
    summary = [{"status": g["_id"], "count": g["count"], "overdue_count": g["overdue_count"]} for g in grouped]
    return {"summary": summary}


@router.get("")
@router.get("/")
async def list_tasks(
    mine: str | None = None,
    role: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    filt: dict = {}
    if mine == "true":
        filt["assigned_to"] = current_user["id"]
    elif role:
        filt["assigned_role"] = role
    if status:
        filt["status"] = status
    if priority:
        filt["priority"] = priority

    # Fixed: this used to be `tasks.find(filt).to_list(None)` -- pulling
    # EVERY matching task (platform-wide across every business/partner
    # verification/content/SEO/CRM/support task ever created, with no
    # collection-level bound) into app memory, then sorting all of it in
    # Python, and only THEN slicing to 300. Exactly the "site used to be
    # fast, now it's slow" pattern flagged in db_indexes.py -- this
    # endpoint's cost used to grow with the platform's entire task
    # history, not with what's actually shown. Replaced with an
    # aggregation pipeline that computes the same three-key sort (open
    # before done, urgent before not, earliest SLA due date first) via
    # $addFields + $sort, then $limit(300) at the DB level -- Mongo only
    # ever has to materialize the 300 rows this endpoint actually returns.
    # Naive, not aware -- same reason as tasks_summary's right_now above.
    far_future = (now() + timedelta(days=36500)).replace(tzinfo=None)
    rows = await tasks.aggregate([
        {"$match": filt},
        {"$addFields": {
            "_is_done": {"$eq": ["$status", "done"]},
            "_not_urgent": {"$ne": ["$priority", "urgent"]},
            "_sla_sort": {"$ifNull": ["$sla_due_at", far_future]},
        }},
        {"$sort": {"_is_done": 1, "_not_urgent": 1, "_sla_sort": 1}},
        {"$limit": 300},
        # NOTE: would ideally end with a $unset of the three sort-helper
        # fields here (they're internal to this query, not part of a
        # task's real shape) -- mongomock doesn't implement $unset in
        # aggregation pipelines (raises NotImplementedError), so instead
        # they're stripped in Python just below, right after the fetch.
    ]).to_list(None)
    for r in rows:
        r.pop("_is_done", None)
        r.pop("_not_urgent", None)
        r.pop("_sla_sort", None)

    # Batch-fetch org + assigned-user ONCE each via $in, instead of 2
    # find_one calls per task row -- this used to be a 1 + 2*N query pattern
    # (e.g. 601 queries to render a 300-row page); now it's a fixed 3 queries
    # total no matter how many rows are being enriched.
    org_ids = list({t["org_id"] for t in rows if t.get("org_id")})
    user_ids = list({t["assigned_to"] for t in rows if t.get("assigned_to")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}
    user_docs = await users.find({"_id": {"$in": user_ids}}).to_list(None) if user_ids else []
    users_by_id = {u["_id"]: u for u in user_docs}

    out = []
    for t in rows:
        org = orgs_by_id.get(t.get("org_id"))
        au = users_by_id.get(t.get("assigned_to"))
        item = to_out(t)
        item["org_name"] = org.get("name") if org else None
        item["assigned_to_name"] = au.get("name") if au else None
        item["is_overdue"] = bool(t.get("sla_due_at") and as_aware(t["sla_due_at"]) < now() and t["status"] != "done")
        out.append(item)
    return {"tasks": out}


class CreateTaskBody(BaseModel):
    orgId: str | None = None
    title: str
    description: str | None = None
    taskType: str
    assignedRole: str | None = None
    assignedTo: str | None = None
    priority: str | None = None
    slaHours: int | None = None
    relatedType: str | None = None
    relatedId: str | None = None


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_task(body: CreateTaskBody, current_user: dict = Depends(get_current_user)):
    sla_hours = body.slaHours or 24
    doc = {
        "_id": new_id(), "org_id": body.orgId, "related_type": body.relatedType,
        "related_id": body.relatedId, "title": body.title, "description": body.description,
        "task_type": body.taskType, "assigned_role": body.assignedRole, "assigned_to": body.assignedTo,
        "priority": body.priority or "normal", "status": "open", "sla_hours": sla_hours,
        "sla_due_at": now() + timedelta(hours=sla_hours), "created_by": current_user["id"],
        "completed_at": None, "created_at": now(),
    }
    await tasks.insert_one(doc)

    if body.assignedTo:
        await notify(body.assignedTo, "task_assigned", "New task assigned", body.title, "task", doc["_id"])
    await log_audit(current_user["id"], "task.created", "task", doc["_id"])
    return {"task": to_out(doc)}


class PatchTaskBody(BaseModel):
    status: str | None = None
    assignedTo: str | None = None
    priority: str | None = None


TASK_STATUSES = ("open", "in_progress", "done")


@router.patch("/{task_id}")
async def patch_task(task_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    updates = {}
    if body.get("status"):
        # Fixed: any string was accepted with no check against the
        # statuses the rest of the app actually produces/understands --
        # "open" (create_task's default), "in_progress" (Tasks.jsx's
        # claim()), and "done" (checked explicitly by dashboard.py's
        # overdue counters and this file's own is_overdue/tasks_summary
        # logic). A typo like "donee" saved silently and then never
        # counted as complete anywhere -- same validation gap already
        # closed for queue.py's status field.
        if body["status"] not in TASK_STATUSES:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(TASK_STATUSES)}.")
        updates["status"] = body["status"]
        if body["status"] == "done":
            updates["completed_at"] = now()
    if "assignedTo" in body:
        updates["assigned_to"] = body["assignedTo"]
    if body.get("priority"):
        updates["priority"] = body["priority"]
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    result = await tasks.update_one({"_id": task_id}, {"$set": updates})
    updated = await tasks.find_one({"_id": task_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Task not found.")

    await log_audit(current_user["id"], "task.updated", "task", task_id, body)
    return {"task": to_out(updated)}

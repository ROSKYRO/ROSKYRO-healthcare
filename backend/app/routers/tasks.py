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
    filt = {"assigned_role": role} if role else {}
    rows = await tasks.find(filt).to_list(None)
    by_status: dict = {}
    for t in rows:
        s = t["status"]
        entry = by_status.setdefault(s, {"status": s, "count": 0, "overdue_count": 0})
        entry["count"] += 1
        if t.get("sla_due_at") and as_aware(t["sla_due_at"]) < now() and s != "done":
            entry["overdue_count"] += 1
    return {"summary": list(by_status.values())}


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

    rows = await tasks.find(filt).to_list(None)

    def sort_key(t):
        return (t["status"] == "done", t.get("priority") != "urgent", as_aware(t.get("sla_due_at")) or now() + timedelta(days=36500))
    rows.sort(key=sort_key)
    rows = rows[:300]

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


@router.patch("/{task_id}")
async def patch_task(task_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    updates = {}
    if body.get("status"):
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

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
    roster = []
    for u in all_users:
        open_tasks = await tasks.count_documents({"assigned_to": u["_id"], "status": {"$ne": "done"}})
        overdue_tasks = await tasks.count_documents({
            "assigned_to": u["_id"], "status": {"$ne": "done"}, "sla_due_at": {"$lt": now()},
        })
        completed_tasks = await tasks.count_documents({"assigned_to": u["_id"], "status": "done"})
        roster.append({
            "id": u["_id"], "name": u.get("name"), "email": u.get("email"),
            "role": u.get("role"), "status": u.get("status"),
            "open_tasks": open_tasks, "overdue_tasks": overdue_tasks, "completed_tasks": completed_tasks,
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

    out = []
    for t in rows:
        org = await organizations.find_one({"_id": t["org_id"]}) if t.get("org_id") else None
        au = await users.find_one({"_id": t["assigned_to"]}) if t.get("assigned_to") else None
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

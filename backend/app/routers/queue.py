from fastapi import APIRouter, HTTPException, Depends

from app.db import queue_entries
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/queue", tags=["queue"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


@router.get("")
@router.get("/")
async def list_queue(orgId: str | None = None, current_user: dict = Depends(get_current_user)):
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else orgId
    if not org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")

    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await queue_entries.find({"org_id": org_id, "checked_in_at": {"$gte": today_start}}).to_list(None)
    rows.sort(key=lambda e: e.get("token_number") or 0)
    return {"queue": to_out_many(rows)}


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def check_in(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can manage the queue.")
    patient_name = body.get("patientName")
    if not patient_name:
        raise HTTPException(status_code=400, detail="patientName is required.")

    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = await queue_entries.find({"org_id": current_user["orgId"], "checked_in_at": {"$gte": today_start}}).to_list(None)
    next_token = max([e.get("token_number") or 0 for e in existing], default=0) + 1

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "appointment_id": body.get("appointmentId"),
        "patient_name": patient_name, "token_number": next_token, "doctor_name": body.get("doctorName"),
        "status": "waiting", "checked_in_at": now(), "called_at": None, "completed_at": None,
    }
    await queue_entries.insert_one(doc)
    return {"entry": to_out(doc)}


@router.patch("/{entry_id}")
async def patch_queue_entry(entry_id: str, body: dict):
    status = body.get("status")
    if status not in ("waiting", "in_consultation", "done", "no_show", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status.")

    updates = {"status": status}
    timestamp_field = {"in_consultation": "called_at", "done": "completed_at"}.get(status)
    if timestamp_field:
        updates[timestamp_field] = now()

    await queue_entries.update_one({"_id": entry_id}, {"$set": updates})
    updated = await queue_entries.find_one({"_id": entry_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Queue entry not found.")
    return {"entry": to_out(updated)}

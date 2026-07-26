from fastapi import APIRouter, HTTPException, Depends

from app.db import queue_entries
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.counters import next_sequence

router = APIRouter(
    prefix="/api/queue", tags=["queue"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


async def _current_max_token(org_id: str, since) -> int:
    """Bootstraps a day's token counter (see check_in below) from whatever
    max token_number already exists for today -- so switching to the
    atomic $inc counter mid-day (after some walk-ins were already checked
    in the old read-then-write way) can't mint a number that collides with
    one already handed out today."""
    existing = await queue_entries.find({"org_id": org_id, "checked_in_at": {"$gte": since}}).to_list(None)
    return max([e.get("token_number") or 0 for e in existing], default=0)


@router.get("")
@router.get("/")
async def list_queue(orgId: str | None = None, current_user: dict = Depends(get_current_user)):
    # Only "customer" (own org) or "internal" with an explicit orgId may
    # scope this query -- a "partner" shell previously fell into the same
    # `else orgId` branch as internal, so a partner account could pass an
    # arbitrary ?orgId= and read another business's data. Fixed: partner
    # (and any other non-customer, non-internal shell) is rejected here.
    if current_user["appShell"] == "customer":
        org_id = current_user["orgId"]
    elif current_user["appShell"] == "internal" and orgId:
        org_id = orgId
    else:
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
    # Atomic $inc per (org, day) counter -- not a read-then-write max() over
    # existing rows, which is a TOCTOU race: two patients checking in at the
    # same instant could both read the same max and be assigned the same
    # token_number. See app/utils/counters.py.
    counter_id = f"queue_token|{current_user['orgId']}|{today_start.date().isoformat()}"
    next_token = await next_sequence(
        counter_id, bootstrap=lambda: _current_max_token(current_user["orgId"], today_start),
    )

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "appointment_id": body.get("appointmentId"),
        "patient_name": patient_name, "token_number": next_token, "doctor_name": body.get("doctorName"),
        "status": "waiting", "checked_in_at": now(), "called_at": None, "completed_at": None,
    }
    await queue_entries.insert_one(doc)
    return {"entry": to_out(doc)}


@router.patch("/{entry_id}")
async def patch_queue_entry(entry_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    """Fixed IDOR: this previously took no current_user and never checked
    ownership, so any authenticated user (any org) could alter ANY
    business's live queue just by guessing/knowing an entry_id -- same bug
    class fixed together across patients.py/billing.py/followups.py/
    appointments.py."""
    existing = await queue_entries.find_one({"_id": entry_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Queue entry not found.")
    if not (
        current_user["appShell"] == "internal"
        or (current_user["appShell"] == "customer" and existing["org_id"] == current_user["orgId"])
    ):
        raise HTTPException(status_code=403, detail="Not authorized.")

    status = body.get("status")
    if status not in ("waiting", "in_consultation", "done", "no_show", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status.")

    updates = {"status": status}
    timestamp_field = {"in_consultation": "called_at", "done": "completed_at"}.get(status)
    if timestamp_field:
        updates[timestamp_field] = now()

    await queue_entries.update_one({"_id": entry_id}, {"$set": updates})
    updated = await queue_entries.find_one({"_id": entry_id})
    return {"entry": to_out(updated)}

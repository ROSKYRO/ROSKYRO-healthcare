from fastapi import APIRouter, HTTPException, Depends

from app.db import doctors
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/doctors", tags=["doctors"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)

# Multispeciality clinics/hospitals have different faculty/doctors
# available on different days and times, so each doctor carries their own
# weekly recurring schedule (a subset of these day keys, each with an
# open/close time) instead of one fixed org-wide window.
DAY_KEYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _validate_schedule(schedule) -> list[dict]:
    if not isinstance(schedule, list):
        raise HTTPException(status_code=400, detail="weeklySchedule must be a list.")
    seen_days = set()
    cleaned = []
    for entry in schedule:
        day = entry.get("day")
        open_time = entry.get("openTime")
        close_time = entry.get("closeTime")
        if day not in DAY_KEYS:
            raise HTTPException(status_code=400, detail=f"Invalid day '{day}' in weekly schedule.")
        if day in seen_days:
            raise HTTPException(status_code=400, detail=f"Duplicate schedule entry for '{day}'.")
        if not open_time or not close_time or str(open_time) >= str(close_time):
            raise HTTPException(status_code=400, detail=f"'{day}': close time must be after open time.")
        seen_days.add(day)
        cleaned.append({"day": day, "open_time": open_time, "close_time": close_time})
    return cleaned


def _assert_owns(existing: dict, current_user: dict, action: str):
    if current_user["appShell"] != "customer" or current_user["orgId"] != existing["org_id"]:
        raise HTTPException(status_code=403, detail=f"Not authorized to {action} this doctor.")
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail=f"Only the business owner can {action} doctors.")


@router.get("")
@router.get("/")
async def list_doctors(orgId: str | None = None, activeOnly: str | None = None, current_user: dict = Depends(get_current_user)):
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else orgId
    if not org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")
    filt: dict = {"org_id": org_id}
    if activeOnly == "true":
        filt["is_active"] = True
    rows = await doctors.find(filt).sort("name", 1).to_list(None)
    return {"doctors": to_out_many(rows)}


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_doctor(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can manage doctors.")
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the business owner can add doctors.")

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required.")
    schedule = _validate_schedule(body.get("weeklySchedule") or [])
    if not schedule:
        raise HTTPException(status_code=400, detail="Add at least one day this doctor is available.")

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "name": name,
        "specialty": (body.get("specialty") or "").strip() or None,
        "consultation_fee": float(body.get("consultationFee") or 0),
        "slot_duration_minutes": int(body.get("slotDurationMinutes") or 30),
        "capacity_per_slot": max(1, int(body.get("capacityPerSlot") or 1)),
        "weekly_schedule": schedule, "is_active": True,
        "created_at": now(), "updated_at": now(),
    }
    await doctors.insert_one(doc)
    await log_audit(current_user["id"], "doctor.created", "doctor", doc["_id"], {"name": name})
    return {"doctor": to_out(doc)}


EDITABLE = {
    "name": "name", "specialty": "specialty", "consultationFee": "consultation_fee",
    "slotDurationMinutes": "slot_duration_minutes", "capacityPerSlot": "capacity_per_slot",
    "isActive": "is_active",
}


@router.patch("/{doctor_id}")
async def update_doctor(doctor_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    existing = await doctors.find_one({"_id": doctor_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    _assert_owns(existing, current_user, "edit")

    updates = {}
    for camel, snake in EDITABLE.items():
        if camel in body:
            updates[snake] = body[camel]
    if "name" in updates and not str(updates["name"]).strip():
        raise HTTPException(status_code=400, detail="name cannot be empty.")
    if "weeklySchedule" in body:
        schedule = _validate_schedule(body["weeklySchedule"])
        if not schedule:
            raise HTTPException(status_code=400, detail="Add at least one day this doctor is available.")
        updates["weekly_schedule"] = schedule
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    updates["updated_at"] = now()

    await doctors.update_one({"_id": doctor_id}, {"$set": updates})
    updated = await doctors.find_one({"_id": doctor_id})
    await log_audit(current_user["id"], "doctor.updated", "doctor", doctor_id, {"fields": list(body.keys())})
    return {"doctor": to_out(updated)}


@router.delete("/{doctor_id}")
async def deactivate_doctor(doctor_id: str, current_user: dict = Depends(get_current_user)):
    """Soft-delete only -- past appointments already reference this doctor
    by name/id, so we deactivate (hide from the public booking picker,
    stop accepting new bookings) rather than hard-delete."""
    existing = await doctors.find_one({"_id": doctor_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Doctor not found.")
    _assert_owns(existing, current_user, "remove")

    await doctors.update_one({"_id": doctor_id}, {"$set": {"is_active": False, "updated_at": now()}})
    await log_audit(current_user["id"], "doctor.deactivated", "doctor", doctor_id)
    return {"ok": True}

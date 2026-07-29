import math
import re

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

# Accepts "HH:MM" or "HH:MM:SS" with real hour/minute ranges. utils/booking.py's
# time_to_minutes() does a bare int(parts[0]) / int(parts[1]) with no guard, so
# anything that isn't this exact shape becomes an IndexError/ValueError there.
#
# The hour's leading zero is deliberately OPTIONAL -- "9:00" is accepted and
# treated identically to "09:00". See the second bullet in _validate_
# schedule's comment below: wrongly rejecting unpadded-but-well-formed times
# is one of the two bugs this regex was introduced to fix, so requiring the
# pad here would have re-introduced it. time_to_minutes() parses either form
# without issue; what it cannot survive is a missing colon or an
# out-of-range component, both of which are still rejected.
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?$")

# A slot can't be shorter than 5 minutes or longer than a 4-hour block. The
# LOWER bound is the load-bearing one -- see _coerce_slot_duration below.
MIN_SLOT_MINUTES = 5
MAX_SLOT_MINUTES = 240
# One doctor physically cannot see more than this many patients in one slot;
# the cap only exists to stop an absurd value from being stored.
MAX_CAPACITY_PER_SLOT = 100


def _to_minutes(value: str) -> int:
    parts = str(value).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def _validate_schedule(schedule) -> list[dict]:
    if not isinstance(schedule, list):
        raise HTTPException(status_code=400, detail="weeklySchedule must be a list.")
    seen_days = set()
    cleaned = []
    for entry in schedule:
        # Fixed: only the OUTER value was checked for being a list -- each
        # entry was assumed to be a dict, so a payload like
        # {"weeklySchedule": ["mon"]} raised an unhandled AttributeError
        # ('str' object has no attribute 'get') and surfaced as a raw 500
        # instead of the intended clean 400.
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail="Each weeklySchedule entry must be an object with day/openTime/closeTime.")
        day = entry.get("day")
        open_time = entry.get("openTime")
        close_time = entry.get("closeTime")
        if day not in DAY_KEYS:
            raise HTTPException(status_code=400, detail=f"Invalid day '{day}' in weekly schedule.")
        if day in seen_days:
            raise HTTPException(status_code=400, detail=f"Duplicate schedule entry for '{day}'.")
        # Fixed: open/close were never format-checked, and were compared as
        # raw STRINGS. Two separate live bugs came out of that one line:
        #   - "0900"/"1700" (any client not using the browser's
        #     <input type="time"> widget -- a script, a mobile client, curl)
        #     passed the lexicographic check and saved 200 OK, after which
        #     utils/booking.py's time_to_minutes() raised IndexError on
        #     int(parts[1]) -- turning the PUBLIC, unauthenticated patient
        #     booking page for this whole business into a permanent 500.
        #   - unpadded "9:00"-"17:00" was WRONGLY rejected with "close time
        #     must be after open time", because the string "9" > "1".
        # Both are gone once the shape is enforced and the comparison is
        # done on minutes-since-midnight instead of on text.
        for label, value in (("openTime", open_time), ("closeTime", close_time)):
            if not isinstance(value, str) or not _TIME_RE.match(value):
                raise HTTPException(status_code=400, detail=f"'{day}': {label} must be in HH:MM 24-hour format (e.g. 09:30).")
        if _to_minutes(open_time) >= _to_minutes(close_time):
            raise HTTPException(status_code=400, detail=f"'{day}': close time must be after open time.")
        seen_days.add(day)
        cleaned.append({"day": day, "open_time": open_time, "close_time": close_time})
    return cleaned


def _coerce_fee(value) -> float:
    """Consultation fee -> a finite, non-negative float.

    Fixed: the old try/except only caught TypeError/ValueError, but
    float("NaN") and float("Infinity") both SUCCEED. A non-finite value was
    therefore written to the doctor document, and every later read that
    serialized it blew up -- FastAPI's JSONResponse renders with
    json.dumps(allow_nan=False), which raises "Out of range float values are
    not JSON compliant". Because the write had already landed, that made
    GET /api/doctors AND the public GET /api/public/booking/{org_id} return
    500 permanently, with no UI path to delete the poisoned row. A negative
    fee is rejected for the same reason settlements.py rejects negative
    amounts: it would be charged to a patient as a negative bill.
    """
    try:
        fee = float(value if value is not None else 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Consultation fee, slot duration and capacity must be numeric.")
    if not math.isfinite(fee):
        raise HTTPException(status_code=400, detail="Consultation fee must be a real number.")
    if fee < 0:
        raise HTTPException(status_code=400, detail="Consultation fee cannot be negative.")
    return fee


def _coerce_slot_duration(value) -> int:
    """Slot length -> an int within [MIN_SLOT_MINUTES, MAX_SLOT_MINUTES].

    Fixed (highest-severity bug in this file): capacityPerSlot was clamped
    with max(1, ...) but slot duration had NO lower bound at all, so a
    negative value saved cleanly with a 201. It then flowed into
    utils/booking.py's generate_slots():

        while t + duration <= close_min:
            slots.append(minutes_to_time(t)); t += duration

    With duration < 0 the loop counter DECREASES, the condition never turns
    false, and minutes_to_time(-10) happily returns "-1:50" rather than
    raising -- so nothing terminates it. Zero hangs identically (t never
    moves). This is reached from GET /api/public/booking/{org}/doctors/{id}/
    availability and POST .../book, which are public and unauthenticated:
    one owner fat-fingering "-5" into the slot-length field pins the CPU
    inside an async handler, blocking the event loop for EVERY tenant on the
    process, while the appended list grows until the OOM killer fires.
    Reproduced: 2,000,000 iterations with no exit; MemoryError in 3.3s under
    a 512 MB cap.
    """
    try:
        minutes = int(value if value not in (None, "") else 30)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Consultation fee, slot duration and capacity must be numeric.")
    if minutes < MIN_SLOT_MINUTES or minutes > MAX_SLOT_MINUTES:
        raise HTTPException(
            status_code=400,
            detail=f"Slot length must be between {MIN_SLOT_MINUTES} and {MAX_SLOT_MINUTES} minutes.",
        )
    return minutes


def _coerce_capacity(value) -> int:
    try:
        capacity = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Consultation fee, slot duration and capacity must be numeric.")
    if capacity > MAX_CAPACITY_PER_SLOT:
        raise HTTPException(status_code=400, detail=f"Patients per slot cannot exceed {MAX_CAPACITY_PER_SLOT}.")
    return max(1, capacity)


def _assert_owns(existing: dict, current_user: dict, action: str):
    if current_user["appShell"] != "customer" or current_user["orgId"] != existing["org_id"]:
        raise HTTPException(status_code=403, detail=f"Not authorized to {action} this doctor.")
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail=f"Only the business owner can {action} doctors.")


@router.get("")
@router.get("/")
async def list_doctors(orgId: str | None = None, activeOnly: str | None = None, current_user: dict = Depends(get_current_user)):
    # Fixed IDOR: previously fell through to `else orgId` for ANY
    # non-customer shell, so a partner account could pass an arbitrary
    # ?orgId= and enumerate another business's doctor roster (names,
    # specialties, consultation fees) -- same bug class as patients.py/
    # whatsapp.py/appointments.py/billing.py/followups.py/queue.py.
    if current_user["appShell"] == "customer":
        org_id = current_user["orgId"]
    elif current_user["appShell"] == "internal" and orgId:
        org_id = orgId
    else:
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

    # A non-numeric consultationFee/slotDurationMinutes/capacityPerSlot
    # previously raised an unhandled ValueError from float()/int() here,
    # surfacing as a raw 500 instead of a clean validation error. Range and
    # finiteness are now enforced too -- see the helpers' own comments for
    # why an unbounded slot duration and a NaN fee were each a live outage.
    consultation_fee = _coerce_fee(body.get("consultationFee"))
    slot_duration_minutes = _coerce_slot_duration(body.get("slotDurationMinutes"))
    capacity_per_slot = _coerce_capacity(body.get("capacityPerSlot"))

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "name": name,
        "specialty": (body.get("specialty") or "").strip() or None,
        "consultation_fee": consultation_fee,
        "slot_duration_minutes": slot_duration_minutes,
        "capacity_per_slot": capacity_per_slot,
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
    # Fixed: create_doctor validates/coerces these three fields with a
    # try/except float()/int() (see its own comment above), but this PATCH
    # handler stored whatever raw value the client sent with no coercion
    # at all -- a non-numeric consultationFee ("abc") saved here isn't
    # rejected, it just sits in the DB as a string until the first patient
    # tries to book this doctor, at which point public_booking.py's
    # book_slot does `float(doctor.get("consultation_fee") or 0)` and
    # crashes with an unhandled ValueError (raw 500) on every booking
    # attempt for that doctor, not just this request. Same class of gap for
    # slotDurationMinutes (feeds utils/booking.py's generate_slots) and
    # capacityPerSlot (compared against an int elsewhere in book_slot).
    # Routed through the same helpers create_doctor uses, so a value that
    # cannot be created also cannot be edited IN afterwards -- previously
    # PATCH re-validated with a weaker copy of the create-side rules.
    if "consultation_fee" in updates:
        updates["consultation_fee"] = _coerce_fee(updates["consultation_fee"])
    if "slot_duration_minutes" in updates:
        updates["slot_duration_minutes"] = _coerce_slot_duration(updates["slot_duration_minutes"])
    if "capacity_per_slot" in updates:
        updates["capacity_per_slot"] = _coerce_capacity(updates["capacity_per_slot"])
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

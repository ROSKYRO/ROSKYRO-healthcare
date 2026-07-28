from fastapi import APIRouter, HTTPException, Depends

from app.db import booking_settings
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out

router = APIRouter(
    prefix="/api/booking-settings", tags=["booking-settings"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)

# Org-wide QR booking controls only. Per-doctor hours/fee/slot-length now
# live on each doctor document (see app/routers/doctors.py) since a
# multispeciality clinic or hospital has different faculty available at
# different times -- there is no longer one single org-wide open/close
# window or one consultation fee.
EDITABLE_FIELDS = {
    "isEnabled": "is_enabled", "upiId": "upi_id", "bookingWindowDays": "booking_window_days",
}

DEFAULTS = {
    "is_enabled": False, "upi_id": None, "booking_window_days": 7, "updated_by": None,
}


@router.get("")
@router.get("/")
async def get_settings(current_user: dict = Depends(get_current_user)):
    """The calling org's settings row (created with sane defaults on first
    fetch, so the admin panel always has something to render even before
    the owner has saved anything)."""
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can manage booking settings.")

    row = await booking_settings.find_one({"org_id": current_user["orgId"]})
    if not row:
        row = {"_id": new_id(), "org_id": current_user["orgId"], **DEFAULTS, "created_at": now(), "updated_at": now()}
        await booking_settings.insert_one(row)
    return {"settings": to_out(row)}


@router.patch("")
@router.patch("/")
async def patch_settings(body: dict, current_user: dict = Depends(get_current_user)):
    """Owner-only. Lets a clinic/hospital control: is the QR link live at
    all, what UPI ID patients pay to, and how many days ahead patients can
    book. Per-doctor hours/fee/slot-length are managed separately, one
    doctor at a time, via /api/doctors."""
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can manage booking settings.")
    if current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the business owner can change booking settings.")

    updates = {}
    for camel, snake in EDITABLE_FIELDS.items():
        if camel in body:
            updates[snake] = body[camel]

    # Fixed: these two were stored completely unvalidated, and both feed
    # code paths on the PUBLIC (unauthenticated, patient-facing) booking
    # router the moment they're bad:
    #   - bookingWindowDays flows straight into utils/booking.py's
    #     upcoming_dates(), which does `range(int(window_days))` -- a
    #     non-numeric value (a stray string, an empty field) crashes with
    #     an unhandled ValueError, taking down BOTH
    #     GET /public/booking/{org}/doctors/{id}/availability AND
    #     POST /public/booking/{org}/{id}/book for every patient, for
    #     every doctor at this business, until an admin manually fixes
    #     the DB row.
    #   - isEnabled is even sneakier: public_booking.py's
    #     _load_org_and_settings checks `not settings.get("is_enabled")`
    #     to decide whether booking is open. In Python, the STRING "false"
    #     is truthy, so `{"isEnabled": "false"}` (e.g. a form/API client
    #     that doesn't send a real JSON boolean) would leave booking
    #     ENABLED -- the exact opposite of what was just "saved" as off.
    if "is_enabled" in updates:
        if not isinstance(updates["is_enabled"], bool):
            raise HTTPException(status_code=400, detail="isEnabled must be true or false.")
    if "booking_window_days" in updates:
        try:
            window_days = int(updates["booking_window_days"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="bookingWindowDays must be a whole number.")
        if window_days < 1:
            raise HTTPException(status_code=400, detail="bookingWindowDays must be at least 1.")
        updates["booking_window_days"] = window_days

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    updates["updated_by"] = current_user["id"]
    updates["updated_at"] = now()

    # Make sure the row exists first (owner may PATCH before ever GET-ing).
    existing = await booking_settings.find_one({"org_id": current_user["orgId"]})
    if not existing:
        await booking_settings.insert_one({"_id": new_id(), "org_id": current_user["orgId"], **DEFAULTS, "created_at": now(), "updated_at": now()})

    await booking_settings.update_one({"org_id": current_user["orgId"]}, {"$set": updates})
    updated = await booking_settings.find_one({"org_id": current_user["orgId"]})

    await log_audit(current_user["id"], "booking_settings.updated", "booking_settings", None, {"orgId": current_user["orgId"], "fields": list(body.keys())})
    return {"settings": to_out(updated)}

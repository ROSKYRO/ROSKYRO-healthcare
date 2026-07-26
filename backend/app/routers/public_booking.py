from fastapi import APIRouter, HTTPException
from pymongo import ReturnDocument

from app.db import organizations, booking_settings, appointments, booking_counters, doctors
from app.utils.booking import doctor_slots_for_date, upcoming_dates
from app.utils.ids import new_id, now, to_out
from app.utils.counters import next_sequence

router = APIRouter(prefix="/api/public/booking", tags=["public-booking"])

# This whole router is intentionally public / no-auth: it's what a patient
# hits after scanning the QR code at the clinic's front desk. Nothing here
# should ever require a login -- a walk-in patient has no ROSKYRO account.
#
# Multispeciality clinics/hospitals have several doctors, each available on
# different days/times (and often at different fees) -- so the booking flow
# here is two steps: pick a doctor (this router's /{org_id} endpoint lists
# the active roster), then fetch and book that specific doctor's slots
# (/{org_id}/doctors/{doctor_id}/availability and .../book).


async def _load_org_and_settings(org_id: str):
    org = await organizations.find_one({"_id": org_id})
    if not org:
        raise HTTPException(status_code=404, detail="This booking link is invalid.")
    settings = await booking_settings.find_one({"org_id": org_id})
    if not settings or not settings.get("is_enabled"):
        raise HTTPException(status_code=404, detail="Online booking is not open for this business right now.")
    return org, settings


@router.get("/{org_id}")
async def get_booking_page(org_id: str):
    """Org info + the active doctor/faculty roster a patient can choose
    from. Availability is fetched per-doctor once one is picked (each
    doctor has their own weekly schedule and fee)."""
    org, settings = await _load_org_and_settings(org_id)

    roster = await doctors.find({"org_id": org_id, "is_active": True}).sort("name", 1).to_list(None)
    doctor_list = [
        {
            "id": d["_id"], "name": d["name"], "specialty": d.get("specialty"),
            "consultationFee": d.get("consultation_fee") or 0,
        }
        for d in roster
    ]

    return {
        "org": {"id": org["_id"], "name": org.get("name"), "businessType": org.get("business_type")},
        "settings": {"upiId": settings.get("upi_id"), "bookingWindowDays": settings.get("booking_window_days")},
        "doctors": doctor_list,
    }


@router.get("/{org_id}/doctors/{doctor_id}/availability")
async def get_doctor_availability(org_id: str, doctor_id: str):
    """A specific doctor's open slots with remaining capacity, for the next
    `booking_window_days` days -- resolved from that doctor's own weekly
    recurring schedule, so days they don't work simply show no slots."""
    org, settings = await _load_org_and_settings(org_id)

    doctor = await doctors.find_one({"_id": doctor_id, "org_id": org_id, "is_active": True})
    if not doctor:
        raise HTTPException(status_code=404, detail="This doctor is not available for booking right now.")

    dates = upcoming_dates(settings["booking_window_days"])
    capacity = doctor.get("capacity_per_slot") or 1

    # How many patients are already booked per (date, time) for THIS doctor
    # so we can show remaining capacity and grey out full slots -- capacity
    # is tracked per doctor, not per org, since each doctor runs their own
    # independent queue.
    booked = await appointments.find({
        "org_id": org_id, "doctor_id": doctor_id, "appointment_date": {"$in": dates}, "status": {"$ne": "cancelled"},
    }).to_list(None)
    booked_map: dict = {}
    for a in booked:
        key = f"{a['appointment_date']}|{str(a.get('appointment_time') or '')[:5]}"
        booked_map[key] = booked_map.get(key, 0) + 1

    days = []
    for date in dates:
        slot_times = doctor_slots_for_date(doctor, date)
        slots = []
        for time in slot_times:
            taken = booked_map.get(f"{date}|{time}", 0)
            slots.append({"time": time, "capacity": capacity, "remaining": max(0, capacity - taken)})
        days.append({"date": date, "slots": slots})

    return {
        "doctor": {
            "id": doctor["_id"], "name": doctor["name"], "specialty": doctor.get("specialty"),
            "consultationFee": doctor.get("consultation_fee") or 0,
        },
        "days": days,
    }


@router.post("/{org_id}/book", status_code=201)
async def book_slot(org_id: str, body: dict):
    """Patient submits their own details, picks a doctor + date + time, and
    is queued in order for that doctor. Called by the frontend only after
    the patient has been shown the clinic's UPI ID and self-confirmed
    payment (or immediately, for a doctor with no consultation fee) -- so
    hitting this endpoint at all means payment is done; there's no
    separate "pending" state to reconcile later. Postgres used `SELECT
    ... FOR UPDATE` to lock the slot's rows before counting so two
    patients booking the same slot at the same instant can't both slip
    past a stale capacity check. Mongo multi-doc transactions need a
    replica set (unavailable with the sandbox's mongomock client), so this
    uses an atomic `find_one_and_update($inc)` on a per-(doctor, date,
    time) counter document instead -- a single-document update is atomic
    at the MongoDB level regardless of transaction support, so two
    concurrent bookings still can't both land in the last open seat. Token
    numbers are sequential per doctor per day, not per org per day -- in a
    multispeciality hospital each doctor runs their own independent queue,
    so "line se booking hoti jayegi" means each doctor's own line, not one
    shared line across every faculty member."""
    patient_name = (body.get("patientName") or "").strip()
    patient_phone = (body.get("patientPhone") or "").strip()
    doctor_id = body.get("doctorId")
    appointment_date = body.get("appointmentDate")
    appointment_time = body.get("appointmentTime")
    note = (body.get("note") or "").strip()

    if not patient_name:
        raise HTTPException(status_code=400, detail="Your name is required.")
    if not patient_phone:
        raise HTTPException(status_code=400, detail="Your phone number is required.")
    if not doctor_id:
        raise HTTPException(status_code=400, detail="Please choose a doctor.")
    if not appointment_date or not appointment_time:
        raise HTTPException(status_code=400, detail="Please choose a date and time slot.")

    org, settings = await _load_org_and_settings(org_id)

    doctor = await doctors.find_one({"_id": doctor_id, "org_id": org_id, "is_active": True})
    if not doctor:
        raise HTTPException(status_code=404, detail="This doctor is not available for booking right now.")

    valid_slots = doctor_slots_for_date(doctor, appointment_date)
    if appointment_time not in valid_slots:
        raise HTTPException(status_code=400, detail="That is not a valid time slot for this doctor.")
    valid_dates = upcoming_dates(settings["booking_window_days"])
    if appointment_date not in valid_dates:
        raise HTTPException(status_code=400, detail="That date is outside the booking window.")

    capacity = doctor.get("capacity_per_slot") or 1
    slot_key = f"slot|{org_id}|{doctor_id}|{appointment_date}|{appointment_time}"
    slot_counter = await booking_counters.find_one_and_update(
        {"_id": slot_key}, {"$inc": {"count": 1}}, upsert=True, return_document=ReturnDocument.AFTER,
    )
    if slot_counter["count"] > capacity:
        # Release the reservation we just took -- this slot is full.
        await booking_counters.update_one({"_id": slot_key}, {"$inc": {"count": -1}})
        raise HTTPException(status_code=409, detail="That slot just filled up — please pick another time.")

    token_key = f"token|{org_id}|{doctor_id}|{appointment_date}"
    token_counter = await booking_counters.find_one_and_update(
        {"_id": token_key}, {"$inc": {"count": 1}}, upsert=True, return_document=ReturnDocument.AFTER,
    )
    token_number = token_counter["count"]

    # A separate, GLOBALLY unique one-time booking code -- distinct from
    # token_number above, which only counts turn-order within one doctor's
    # one day and resets to 1 again tomorrow (so "token 3" exists for
    # every doctor, every day -- useless as a lookup key). This code uses
    # the same atomic $inc sequence pattern as referral codes/invoice
    # numbers (see app/utils/counters.py) so it's never reused across ANY
    # booking, by any doctor, on any day, ever. Shown to the patient
    # alongside their token number so they can give it to front-desk staff
    # later -- e.g. so a referring doctor can pull up this patient's name
    # and phone instantly via GET /appointments/lookup/{booking_code}
    # instead of re-typing them when creating a referral (see
    # ReferralNew.jsx's quick-referral flow).
    booking_seq = await next_sequence("appointment_booking_code", bootstrap=lambda: appointments.count_documents({}))
    booking_code = f"BK-{str(booking_seq).zfill(6)}"

    fee = float(doctor.get("consultation_fee") or 0)
    # The frontend only calls this endpoint after the patient has already
    # been shown the clinic's UPI ID and self-confirmed they've paid (the
    # "Maine Payment Kar Diya — Confirm Booking" step) -- there is no
    # "payment pending" limbo state for QR bookings. A booking is only
    # ever created, and a token only ever issued, once payment is done.
    # Doctors with no consultation fee (fee == 0) skip the payment step
    # entirely and book straight through.
    payment_status = "paid" if fee > 0 else "not_required"

    doc = {
        "_id": new_id(), "org_id": org_id, "patient_name": patient_name, "patient_phone": patient_phone,
        "doctor_id": doctor_id, "doctor_name": doctor.get("name"), "appointment_date": appointment_date,
        "appointment_time": appointment_time, "status": "scheduled", "source": "qr_booking",
        "is_new_patient": True, "revenue_amount": fee, "booked_via": "qr_booking",
        "token_number": token_number, "booking_code": booking_code, "payment_status": payment_status,
        "payment_amount": fee or None, "patient_note": note or None, "created_at": now(),
    }
    await appointments.insert_one(doc)

    return {
        "appointment": to_out(doc),
        "payment": {"collected": True, "upiId": settings.get("upi_id"), "amount": fee} if fee > 0 else {"collected": False},
        "tokenNumber": token_number,
        "bookingCode": booking_code,
        "doctor": {"id": doctor["_id"], "name": doctor["name"], "specialty": doctor.get("specialty")},
    }

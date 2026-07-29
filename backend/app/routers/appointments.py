import io
import math
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from app.db import appointments, booking_counters, organizations
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.patients import safe_resolve_patient_id
from app.utils.ids import new_id, to_out, to_out_many

router = APIRouter(
    prefix="/api/appointments", tags=["appointments"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)

# The same set queue.py and followups.py already whitelist their own status
# values against. Two of these literals are load-bearing elsewhere:
# public_booking.py excludes exactly "cancelled" when counting a slot's
# occupancy, and dashboard.py sums revenue for exactly "completed".
APPOINTMENT_STATUSES = ("scheduled", "confirmed", "completed", "cancelled", "no_show")


def _coerce_money(value, field_label: str) -> float:
    """Fixed: the old try/except caught TypeError/ValueError, but float("NaN")
    and float("Infinity") both SUCCEED -- so a non-finite value was written
    to the appointment document, and only blew up later, on read. FastAPI
    renders with json.dumps(allow_nan=False), which raises "Out of range
    float values are not JSON compliant"; because the insert had already
    committed, that left GET /api/appointments, the Booking Settings page
    and the dashboard revenue sum returning 500 PERMANENTLY, with no UI path
    to delete the poisoned row."""
    try:
        amount = float(value if value not in (None, "") else 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{field_label} must be numeric.")
    if not math.isfinite(amount):
        raise HTTPException(status_code=400, detail=f"{field_label} must be a real number.")
    return amount


async def _release_slot_counter(existing: dict) -> None:
    """Give a cancelled QR booking's seat back to the slot counter.

    Fixed -- this was a real, permanently-worsening divergence between the
    two things that both claim to know whether a slot is free:
      - public_booking.py's availability endpoint computes what's taken from
        the live appointment rows, EXCLUDING status "cancelled";
      - public_booking.py's book endpoint enforces capacity against the
        atomic `booking_counters` document instead.
    Nothing anywhere decremented that counter when an appointment was
    cancelled (grep confirms booking_counters was only ever written inside
    public_booking.py). So: Dr A has capacity 1, patient P books 10:00
    (counter -> 1), the front desk cancels it, availability now advertises
    10:00 as open with remaining: 1, and every patient who picks it gets
    409 "That slot just filled up". That slot was unbookable forever, and
    one more slot broke this way with every cancellation.

    Only QR bookings touch a counter (`booked_via == "qr_booking"`), and the
    guard below stops a double-cancel from pushing the count negative.
    """
    if existing.get("booked_via") != "qr_booking" or existing.get("status") == "cancelled":
        return
    doctor_id = existing.get("doctor_id")
    date = existing.get("appointment_date")
    time = str(existing.get("appointment_time") or "")[:5]
    if not (doctor_id and date and time):
        return
    slot_key = f"slot|{existing['org_id']}|{doctor_id}|{date}|{time}"
    await booking_counters.update_one({"_id": slot_key, "count": {"$gt": 0}}, {"$inc": {"count": -1}})


@router.get("")
@router.get("/")
async def list_appointments(
    orgId: str | None = None, from_: str | None = Query(default=None, alias="from"), to: str | None = None,
    current_user: dict = Depends(get_current_user),
):
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

    filt: dict = {"org_id": org_id}
    date_filt = {}
    if from_:
        date_filt["$gte"] = from_
    if to:
        date_filt["$lte"] = to
    if date_filt:
        filt["appointment_date"] = date_filt

    # Push the sort + 200-row cap down into Mongo instead of fetching every
    # matching appointment (which could be tens of thousands for an old
    # business) and sorting/discarding in Python -- same result, the DB
    # does the work using the (org_id, appointment_date) index instead of
    # shipping the whole collection over the wire on every page load.
    rows = await appointments.find(filt).sort(
        [("appointment_date", -1), ("appointment_time", -1)]
    ).limit(200).to_list(None)
    return {"appointments": to_out_many(rows)}


@router.get("/lookup/{booking_code}")
async def lookup_by_booking_code(booking_code: str, current_user: dict = Depends(get_current_user)):
    """Powers the quick-referral flow's booking-code auto-fill (see
    ReferralNew.jsx): typing/scanning the unique code a patient got at QR
    self-booking (see routers/public_booking.py's book_slot) pulls up
    their name and phone instead of re-typing them. Scoped to the calling
    business's own org, same as every other appointments endpoint -- a
    code from one business's QR booking can't be used to pull up a
    patient at another. Only ever matches QR bookings (manually-created
    appointments via POST below never get a booking_code), which is
    exactly the "no booking id -> fill it in by hand" fallback case."""
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else None
    if not org_id:
        raise HTTPException(status_code=400, detail="Only a healthcare business user can look up a booking.")

    appt = await appointments.find_one({"org_id": org_id, "booking_code": booking_code.strip().upper()})
    if not appt:
        raise HTTPException(status_code=404, detail="No booking found with that code -- enter the patient's details manually.")
    return {"appointment": to_out(appt)}


@router.get("/daily-pdf")
async def daily_paid_appointments_pdf(
    date: str = Query(..., description="YYYY-MM-DD"),
    orgId: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Per-day PDF export of paid appointment bookings. Available to any
    business using the appointment booking system (MANAGE pillar, already
    gated by require_plan("manage") above) -- no business_type restriction,
    per the user's explicit clarification that this isn't limited to
    dr./clinic/hospital accounts only.

    NOTE on scope: the user separately asked that if "this appointment's
    service is also taken by another listed partner, they should also get
    it" -- appointments currently have no link to a referral/partner record
    in the data model (no referral_id / partner_id field on the appointment
    doc), so there's no existing structural way to know which partner, if
    any, is associated with a given appointment. Rather than guess at a new
    linkage, this endpoint implements the clear, unambiguous part of the
    request (a business's own paid appointments, any day, as a PDF) and
    intentionally does not attempt the partner-sharing clause -- that needs
    a product decision on how appointments and partners/referrals should be
    linked before it can be built correctly and privacy-safely.
    """
    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format.")

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

    org = await organizations.find_one({"_id": org_id})
    rows = await appointments.find({
        "org_id": org_id, "appointment_date": date, "payment_status": "paid",
    }).to_list(None)
    rows.sort(key=lambda a: (a.get("appointment_time") or ""))

    # reportlab's PDF rendering is synchronous, CPU-bound work -- run it in
    # a worker thread rather than inline on the event loop, so generating
    # one business's PDF doesn't stall every other concurrent request on
    # this (single-worker) server for the duration of the render.
    pdf_bytes = await run_in_threadpool(_render_daily_appointments_pdf, org.get("name") if org else "ROSKYRO", day, rows)
    filename = f"paid-appointments-{date}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _render_daily_appointments_pdf(org_name: str, day, rows: list[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"<b>{org_name}</b>", styles["Title"]),
        Paragraph(f"Paid Appointment Bookings — {day.strftime('%d %b %Y')}", styles["Heading2"]),
        Spacer(1, 6 * mm),
    ]

    total = sum(float(r.get("payment_amount") or r.get("revenue_amount") or 0) for r in rows)
    data = [["Time", "Patient", "Doctor", "Source", "Amount Paid (₹)"]]
    for r in rows:
        amount = float(r.get("payment_amount") or r.get("revenue_amount") or 0)
        data.append([
            (r.get("appointment_time") or "—")[:5],
            r.get("patient_name") or "—",
            r.get("doctor_name") or "—",
            (r.get("source") or "—").replace("_", " "),
            f"{amount:,.2f}",
        ])
    if not rows:
        data.append(["—", "No paid appointments for this date.", "", "", ""])

    table = Table(data, colWidths=[20 * mm, 50 * mm, 45 * mm, 30 * mm, 30 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5dd")),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(f"<b>Total collected: ₹{total:,.2f}</b> across {len(rows)} paid appointment(s).", styles["Normal"]))
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph(
        "Generated by ROSKYRO Healthcare OS. This is an internal daily collection summary, not a tax invoice.",
        styles["Normal"],
    ))

    doc.build(elements)
    return buf.getvalue()


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_appointment(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can create appointments.")
    patient_name = body.get("patientName")
    appointment_date = body.get("appointmentDate")
    if not patient_name or not appointment_date:
        raise HTTPException(status_code=400, detail="patientName and appointmentDate are required.")
    # Fixed: revenueAmount was stored completely unvalidated -- a non-
    # numeric value (e.g. a stray string from a form bug) sailed through
    # here, then crashed with an unhandled ValueError the moment ANYTHING
    # downstream did float(revenue_amount): this file's own revenue-total
    # endpoint (line ~157/160) and dashboard.py's monthly revenue sum both
    # do exactly that, so one bad appointment could take down the whole
    # business's dashboard and revenue report, not just this request.
    # Hardened further: float() happily accepts the strings "NaN" and
    # "Infinity", so the old coercion let a NaN through into the document.
    # FastAPI serialises with json.dumps(allow_nan=False), which then raises
    # AFTER the row is already written -- permanently 500-ing every list /
    # revenue / dashboard response for that business, with no UI path to
    # delete the poisoned row. _coerce_money rejects it at the door.
    revenue_amount = _coerce_money(body.get("revenueAmount"), "revenueAmount")

    # Round 19: bind this appointment to a real patient record instead of
    # leaving a bare name string behind. patients.py's history view joins
    # on this id, so without it two same-named patients at the same clinic
    # end up sharing one clinical timeline. Never fails the booking --
    # see safe_resolve_patient_id()'s docstring.
    patient_id = await safe_resolve_patient_id(
        current_user["orgId"], patient_name, body.get("patientPhone")
    )

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "patient_name": patient_name,
        "patient_id": patient_id,
        "patient_phone": body.get("patientPhone"), "doctor_name": body.get("doctorName"),
        "appointment_date": appointment_date, "appointment_time": body.get("appointmentTime"),
        "status": "scheduled", "source": body.get("source") or "walk_in",
        "is_new_patient": bool(body.get("isNewPatient")), "revenue_amount": revenue_amount,
        "booked_via": None, "token_number": None, "payment_status": "not_required",
        "payment_amount": None, "patient_note": None,
    }
    await appointments.insert_one(doc)
    return {"appointment": to_out(doc)}


@router.patch("/{appointment_id}")
async def patch_appointment(appointment_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    """Fixed IDOR: this previously took no current_user and never checked
    ownership, so any authenticated user (any org) could rewrite ANY
    business's appointment status/revenue/payment just by guessing/knowing
    an appointment_id -- same bug class fixed together across patients.py/
    billing.py/followups.py/queue.py."""
    existing = await appointments.find_one({"_id": appointment_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    if not (
        current_user["appShell"] == "internal"
        or (current_user["appShell"] == "customer" and existing["org_id"] == current_user["orgId"])
    ):
        raise HTTPException(status_code=403, detail="Not authorized.")

    updates = {}
    if body.get("status"):
        # Fixed: status was written through completely unvalidated, unlike
        # every sibling router (queue.py and followups.py both whitelist).
        # A typo'd value such as "canceled" (one 'l') returned 200 OK, but
        # every consumer matches on the exact string "cancelled": the
        # appointment stayed counted as occupying its slot in the public
        # availability calculation AND silently dropped out of the revenue
        # report -- a wrong number on the owner's dashboard with no error
        # anywhere to trace it back to.
        if body["status"] not in APPOINTMENT_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(APPOINTMENT_STATUSES)}.",
            )
        updates["status"] = body["status"]
    if "revenueAmount" in body:
        # Same fix as create_appointment above -- this used to pass the
        # raw client value straight through with no numeric coercion.
        updates["revenue_amount"] = _coerce_money(body["revenueAmount"], "revenueAmount")
    if body.get("paymentStatus"):
        if body["paymentStatus"] not in ("not_required", "pending", "paid"):
            raise HTTPException(status_code=400, detail="Invalid paymentStatus.")
        updates["payment_status"] = body["paymentStatus"]
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    await appointments.update_one({"_id": appointment_id}, {"$set": updates})
    # Cancelling a QR booking must give its seat back. Slot availability on
    # the public booking page is computed from live appointments (excluding
    # "cancelled"), but the actual booking is gated by an atomic counter in
    # booking_counters -- and nothing ever decremented that counter on
    # cancellation. So the slot displayed as FREE to the next patient while
    # the counter still said FULL, and every attempt to book it 409'd
    # forever. The divergence was permanent and grew with every cancellation.
    if updates.get("status") == "cancelled":
        await _release_slot_counter(existing)
    updated = await appointments.find_one({"_id": appointment_id})
    return {"appointment": to_out(updated)}

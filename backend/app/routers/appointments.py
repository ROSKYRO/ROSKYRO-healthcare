from fastapi import APIRouter, HTTPException, Depends, Query

from app.db import appointments
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, to_out, to_out_many

router = APIRouter(
    prefix="/api/appointments", tags=["appointments"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


@router.get("")
@router.get("/")
async def list_appointments(
    orgId: str | None = None, from_: str | None = Query(default=None, alias="from"), to: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else orgId
    if not org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")

    filt: dict = {"org_id": org_id}
    date_filt = {}
    if from_:
        date_filt["$gte"] = from_
    if to:
        date_filt["$lte"] = to
    if date_filt:
        filt["appointment_date"] = date_filt

    rows = await appointments.find(filt).to_list(None)
    rows.sort(key=lambda a: (a.get("appointment_date") or "", a.get("appointment_time") or ""), reverse=True)
    return {"appointments": to_out_many(rows[:200])}


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_appointment(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can create appointments.")
    patient_name = body.get("patientName")
    appointment_date = body.get("appointmentDate")
    if not patient_name or not appointment_date:
        raise HTTPException(status_code=400, detail="patientName and appointmentDate are required.")

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "patient_name": patient_name,
        "patient_phone": body.get("patientPhone"), "doctor_name": body.get("doctorName"),
        "appointment_date": appointment_date, "appointment_time": body.get("appointmentTime"),
        "status": "scheduled", "source": body.get("source") or "walk_in",
        "is_new_patient": bool(body.get("isNewPatient")), "revenue_amount": body.get("revenueAmount") or 0,
        "booked_via": None, "token_number": None, "payment_status": "not_required",
        "payment_amount": None, "patient_note": None,
    }
    await appointments.insert_one(doc)
    return {"appointment": to_out(doc)}


@router.patch("/{appointment_id}")
async def patch_appointment(appointment_id: str, body: dict):
    updates = {}
    if body.get("status"):
        updates["status"] = body["status"]
    if "revenueAmount" in body:
        updates["revenue_amount"] = body["revenueAmount"]
    if body.get("paymentStatus"):
        if body["paymentStatus"] not in ("not_required", "pending", "paid"):
            raise HTTPException(status_code=400, detail="Invalid paymentStatus.")
        updates["payment_status"] = body["paymentStatus"]
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    await appointments.update_one({"_id": appointment_id}, {"$set": updates})
    updated = await appointments.find_one({"_id": appointment_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    return {"appointment": to_out(updated)}

from fastapi import APIRouter, HTTPException, Depends

from app.db import patients, appointments, patient_followups, invoices, whatsapp_messages
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/patients", tags=["patients"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


@router.get("")
@router.get("/")
async def list_patients(orgId: str | None = None, q: str | None = None, current_user: dict = Depends(get_current_user)):
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else orgId
    if not org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")

    filt: dict = {"org_id": org_id}
    if q:
        filt["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"phone": {"$regex": q, "$options": "i"}},
        ]
    rows = await patients.find(filt).sort("updated_at", -1).limit(300).to_list(None)
    return {"patients": to_out_many(rows)}


@router.get("/{patient_id}")
async def get_patient(patient_id: str, current_user: dict = Depends(get_current_user)):
    p = await patients.find_one({"_id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found.")
    if current_user["appShell"] == "customer" and p["org_id"] != current_user["orgId"]:
        raise HTTPException(status_code=403, detail="Not authorized.")

    appts = await appointments.find({"org_id": p["org_id"], "patient_name": p["name"]}).sort("appointment_date", -1).limit(20).to_list(None)
    fups = await patient_followups.find({"org_id": p["org_id"], "patient_name": p["name"]}).sort("due_date", -1).limit(20).to_list(None)
    invs = await invoices.find({"org_id": p["org_id"], "patient_name": p["name"]}).sort("created_at", -1).limit(20).to_list(None)
    wa = await whatsapp_messages.find({"org_id": p["org_id"], "patient_name": p["name"]}).sort("created_at", -1).limit(20).to_list(None)

    return {
        "patient": to_out(p), "appointments": to_out_many(appts), "followups": to_out_many(fups),
        "invoices": to_out_many(invs), "whatsapp": to_out_many(wa),
    }


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_patient(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can add patients.")
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required.")

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "name": name,
        "phone": body.get("phone"), "email": body.get("email"), "age": body.get("age"),
        "gender": body.get("gender"), "tags": body.get("tags"), "notes": body.get("notes"),
        "last_visit_at": None, "total_visits": 0, "lifetime_value": 0,
        "created_at": now(), "updated_at": now(),
    }
    await patients.insert_one(doc)
    return {"patient": to_out(doc)}


ALLOWED_PATCH = {
    "name": "name", "phone": "phone", "email": "email", "age": "age", "gender": "gender",
    "tags": "tags", "notes": "notes", "lastVisitAt": "last_visit_at",
    "totalVisits": "total_visits", "lifetimeValue": "lifetime_value",
}


@router.patch("/{patient_id}")
async def patch_patient(patient_id: str, body: dict):
    updates = {}
    for camel, snake in ALLOWED_PATCH.items():
        if camel in body:
            updates[snake] = body[camel]
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    updates["updated_at"] = now()

    await patients.update_one({"_id": patient_id}, {"$set": updates})
    updated = await patients.find_one({"_id": patient_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return {"patient": to_out(updated)}

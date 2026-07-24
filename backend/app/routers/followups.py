from fastapi import APIRouter, HTTPException, Depends

from app.db import patient_followups
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/followups", tags=["followups"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


@router.get("")
@router.get("/")
async def list_followups(orgId: str | None = None, status: str | None = None, current_user: dict = Depends(get_current_user)):
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else orgId
    if not org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")

    filt: dict = {"org_id": org_id}
    if status:
        filt["status"] = status
    rows = await patient_followups.find(filt).sort("due_date", 1).limit(300).to_list(None)
    return {"followups": to_out_many(rows)}


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_followup(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can create follow-ups.")
    patient_name, reason, due_date = body.get("patientName"), body.get("reason"), body.get("dueDate")
    if not patient_name or not reason or not due_date:
        raise HTTPException(status_code=400, detail="patientName, reason and dueDate are required.")

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "patient_name": patient_name,
        "patient_phone": body.get("patientPhone"), "reason": reason, "due_date": due_date,
        "notes": body.get("notes"), "status": "pending", "completed_at": None,
        "created_by": current_user["id"], "created_at": now(),
    }
    await patient_followups.insert_one(doc)
    return {"followup": to_out(doc)}


@router.patch("/{followup_id}")
async def patch_followup(followup_id: str, body: dict):
    updates = {}
    if body.get("status"):
        if body["status"] not in ("pending", "contacted", "done", "missed"):
            raise HTTPException(status_code=400, detail="Invalid status.")
        updates["status"] = body["status"]
        if body["status"] == "done":
            updates["completed_at"] = now()
    if "notes" in body:
        updates["notes"] = body["notes"]
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    await patient_followups.update_one({"_id": followup_id}, {"$set": updates})
    updated = await patient_followups.find_one({"_id": followup_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Follow-up not found.")
    return {"followup": to_out(updated)}

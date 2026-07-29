from fastapi import APIRouter, HTTPException, Depends

from app.db import patient_followups
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.patients import safe_resolve_patient_id
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/followups", tags=["followups"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


@router.get("")
@router.get("/")
async def list_followups(orgId: str | None = None, status: str | None = None, current_user: dict = Depends(get_current_user)):
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

    # Round 19: see the same call in appointments.py's create_appointment --
    # a follow-up has to hang off a patient id, not a name string, or it
    # surfaces on a same-named stranger's history page.
    patient_id = await safe_resolve_patient_id(
        current_user["orgId"], patient_name, body.get("patientPhone")
    )

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "patient_name": patient_name,
        "patient_id": patient_id,
        "patient_phone": body.get("patientPhone"), "reason": reason, "due_date": due_date,
        "notes": body.get("notes"), "status": "pending", "completed_at": None,
        "created_by": current_user["id"], "created_at": now(),
    }
    await patient_followups.insert_one(doc)
    return {"followup": to_out(doc)}


@router.patch("/{followup_id}")
async def patch_followup(followup_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    """Fixed IDOR: this previously took no current_user and never checked
    ownership, so any authenticated user (any org) could rewrite ANY
    business's patient follow-up record just by guessing/knowing a
    followup_id -- same bug class fixed together across patients.py/
    billing.py/queue.py/appointments.py."""
    existing = await patient_followups.find_one({"_id": followup_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Follow-up not found.")
    if not (
        current_user["appShell"] == "internal"
        or (current_user["appShell"] == "customer" and existing["org_id"] == current_user["orgId"])
    ):
        raise HTTPException(status_code=403, detail="Not authorized.")

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
    return {"followup": to_out(updated)}

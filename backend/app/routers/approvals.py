from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import approvals, organizations, users
from app.auth import get_current_user, require_internal
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(prefix="/api/approvals", tags=["approvals"], dependencies=[Depends(get_current_user)])


@router.get("")
@router.get("/")
async def list_approvals(status: str | None = None, orgId: str | None = None, current_user: dict = Depends(get_current_user)):
    filt: dict = {}
    if current_user["appShell"] == "customer":
        filt["org_id"] = current_user["orgId"]
    elif current_user["appShell"] == "internal" and orgId:
        # Restricted to internal -- a partner-shell account has no
        # legitimate approvals of its own and previously could pass an
        # arbitrary ?orgId= here (same fallback internal used) to read
        # another business's pending-approval queue.
        filt["org_id"] = orgId
    elif current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="Not authorized.")
    if status:
        filt["status"] = status

    rows = await approvals.find(filt).sort("created_at", -1).limit(200).to_list(None)

    # Batch-fetch org + preparer ONCE each via $in, instead of 2 find_one
    # calls per approval row -- same fix as tasks.py/list_tasks: a fixed 3
    # queries total regardless of row count, instead of 1 + 2*N.
    org_ids = list({a["org_id"] for a in rows if a.get("org_id")})
    user_ids = list({a["prepared_by"] for a in rows if a.get("prepared_by")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}
    user_docs = await users.find({"_id": {"$in": user_ids}}).to_list(None) if user_ids else []
    users_by_id = {u["_id"]: u for u in user_docs}

    out = []
    for a in rows:
        org = orgs_by_id.get(a.get("org_id"))
        pu = users_by_id.get(a.get("prepared_by"))
        item = to_out(a)
        item["org_name"] = org.get("name") if org else None
        item["prepared_by_name"] = pu.get("name") if pu else None
        out.append(item)
    return {"approvals": out}


class CreateApprovalBody(BaseModel):
    orgId: str
    approvalType: str
    title: str
    description: str | None = None
    aiGenerated: bool = True


@router.post("", status_code=201, dependencies=[Depends(require_internal)])
@router.post("/", status_code=201, dependencies=[Depends(require_internal)])
async def create_approval(body: CreateApprovalBody, current_user: dict = Depends(get_current_user)):
    doc = {
        "_id": new_id(), "org_id": body.orgId, "approval_type": body.approvalType,
        "title": body.title, "description": body.description,
        "ai_generated": body.aiGenerated is not False, "prepared_by": current_user["id"],
        "status": "pending", "decided_by": None, "decided_at": None, "created_at": now(),
    }
    await approvals.insert_one(doc)

    owner = await users.find_one({"org_id": body.orgId, "role": "owner"})
    if owner:
        await notify(owner["_id"], "approval_pending", "New item awaiting your approval", body.title, "approval", doc["_id"])
    await log_audit(current_user["id"], "approval.created", "approval", doc["_id"])
    return {"approval": to_out(doc)}


class DecisionBody(BaseModel):
    decision: str


@router.post("/{approval_id}/decision")
async def decide_approval(approval_id: str, body: DecisionBody, current_user: dict = Depends(get_current_user)):
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'.")

    existing = await approvals.find_one({"_id": approval_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Approval not found.")
    # Fixed: previously only blocked a customer from a DIFFERENT org, so a
    # partner-shell account (appShell == "partner") never matched that
    # condition and could approve/reject ANY business's pending approval.
    if not (
        current_user["appShell"] == "internal"
        or (current_user["appShell"] == "customer" and existing["org_id"] == current_user["orgId"])
    ):
        raise HTTPException(status_code=403, detail="Not authorized.")

    await approvals.update_one({"_id": approval_id}, {"$set": {
        "status": body.decision, "decided_by": current_user["id"], "decided_at": now(),
    }})
    updated = await approvals.find_one({"_id": approval_id})
    await log_audit(current_user["id"], f"approval.{body.decision}", "approval", approval_id)
    return {"approval": to_out(updated)}

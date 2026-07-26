from fastapi import APIRouter, HTTPException, Depends

from app.db import reviews
from app.auth import get_current_user, require_internal
from app.utils.plans import require_plan
from app.utils.audit import log_audit
from app.utils.ids import now, to_out, to_out_many

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("", dependencies=[Depends(get_current_user), Depends(require_plan("grow"))])
@router.get("/", dependencies=[Depends(get_current_user), Depends(require_plan("grow"))])
async def list_reviews(orgId: str | None = None, current_user: dict = Depends(get_current_user)):
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
    rows = await reviews.find({"org_id": org_id}).sort("created_at", -1).limit(200).to_list(None)
    return {"reviews": to_out_many(rows)}


@router.post("/{review_id}/draft-reply", dependencies=[Depends(require_internal)])
async def draft_reply(review_id: str, body: dict):
    """Internal Review Manager drafts an AI reply, which is then edited by
    a human before it's ever attributed to the business."""
    await reviews.update_one({"_id": review_id}, {"$set": {
        "ai_reply_draft": body.get("aiReplyDraft"), "status": "pending_response",
    }})
    updated = await reviews.find_one({"_id": review_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Review not found.")
    return {"review": to_out(updated)}


@router.post("/{review_id}/publish-reply", dependencies=[Depends(require_internal)])
async def publish_reply(review_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    human_reply = body.get("humanReply")
    if not human_reply:
        raise HTTPException(status_code=400, detail="humanReply is required.")

    await reviews.update_one({"_id": review_id}, {"$set": {
        "human_reply": human_reply, "replied_by": current_user["id"], "status": "published",
    }})
    updated = await reviews.find_one({"_id": review_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Review not found.")

    await log_audit(current_user["id"], "review.reply_published", "review", review_id)
    return {"review": to_out(updated)}

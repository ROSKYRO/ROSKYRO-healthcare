from fastapi import APIRouter, HTTPException, Depends

from app.db import reports
from app.auth import get_current_user, require_internal
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("", dependencies=[Depends(get_current_user), Depends(require_plan("grow"))])
@router.get("/", dependencies=[Depends(get_current_user), Depends(require_plan("grow"))])
async def list_reports(orgId: str | None = None, current_user: dict = Depends(get_current_user)):
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else orgId
    if not org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")
    rows = await reports.find({"org_id": org_id}).sort("period_month", -1).limit(24).to_list(None)
    return {"reports": to_out_many(rows)}


@router.post("", status_code=201, dependencies=[Depends(require_internal)])
@router.post("/", status_code=201, dependencies=[Depends(require_internal)])
async def create_report(body: dict, current_user: dict = Depends(get_current_user)):
    """Internal team generates/publishes the monthly growth report after
    reviewing the AI-compiled numbers (AI + Human step made explicit)."""
    org_id, period_month = body.get("orgId"), body.get("periodMonth")
    if not org_id or not period_month:
        raise HTTPException(status_code=400, detail="orgId and periodMonth are required.")

    doc = {
        "_id": new_id(), "org_id": org_id, "report_type": "monthly_growth", "period_month": period_month,
        "summary": body.get("summary"), "file_url": body.get("fileUrl"), "generated_by": current_user["id"],
        "created_at": now(),
    }
    await reports.insert_one(doc)
    return {"report": to_out(doc)}

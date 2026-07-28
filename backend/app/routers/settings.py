from fastapi import APIRouter, Depends, HTTPException

from app.db import platform_settings
from app.auth import get_current_user, require_roles
from app.utils.audit import log_audit
from app.utils.ids import now

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/payment")
async def get_payment_settings():
    """Public: the UPI ID shown on the subscribe / checkout step. No auth
    required so the "how do I pay" info can render before a business has
    even registered."""
    row = await platform_settings.find_one({"_id": 1})
    if not row:
        return {"upi_id": None, "payment_note": None}
    return {"upi_id": row.get("upi_id"), "payment_note": row.get("payment_note"), "updated_at": row.get("updated_at")}


@router.patch("/payment", dependencies=[Depends(require_roles("roskyro_admin"))])
async def patch_payment_settings(body: dict, current_user: dict = Depends(get_current_user)):
    upi_id = (body.get("upiId") or "").strip()
    if not upi_id:
        raise HTTPException(status_code=400, detail="upiId is required.")

    # Fixed: "paymentNote omitted from the request" and "paymentNote sent
    # as an empty string" both collapsed to the same `None`, and `None`
    # only ever got written to the $set on first-ever creation (`elif not
    # existing`). So once a note existed, an admin trying to CLEAR it by
    # submitting an empty paymentNote silently no-opped -- the PATCH
    # returned 200 with no error, but the old note stayed forever. Now the
    # two cases are distinguished by whether the key was sent at all.
    updates = {"upi_id": upi_id, "updated_by": current_user["id"], "updated_at": now()}
    if "paymentNote" in body:
        updates["payment_note"] = (body.get("paymentNote") or "").strip() or None
    else:
        existing = await platform_settings.find_one({"_id": 1})
        if not existing:
            updates["payment_note"] = None

    await platform_settings.update_one({"_id": 1}, {"$set": updates}, upsert=True)
    updated = await platform_settings.find_one({"_id": 1})
    await log_audit(current_user["id"], "settings.payment_updated", "platform_settings", None, {"upiId": upi_id})
    return updated

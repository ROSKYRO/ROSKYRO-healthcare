from fastapi import APIRouter, HTTPException, Depends

from app.db import notifications
from app.auth import get_current_user
from app.utils.ids import to_out, to_out_many

router = APIRouter(prefix="/api/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)])


@router.get("")
@router.get("/")
async def list_notifications(current_user: dict = Depends(get_current_user)):
    rows = await notifications.find({"user_id": current_user["id"]}).sort("created_at", -1).limit(50).to_list(None)
    return {"notifications": to_out_many(rows)}


@router.post("/{notification_id}/read")
async def mark_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    result = await notifications.update_one(
        {"_id": notification_id, "user_id": current_user["id"]}, {"$set": {"is_read": True}}
    )
    updated = await notifications.find_one({"_id": notification_id, "user_id": current_user["id"]})
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return {"notification": to_out(updated)}


@router.post("/read-all")
async def mark_all_read(current_user: dict = Depends(get_current_user)):
    await notifications.update_many(
        {"user_id": current_user["id"], "is_read": False}, {"$set": {"is_read": True}}
    )
    return {"ok": True}

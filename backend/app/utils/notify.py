from app.db import notifications
from app.utils.ids import new_id, now


async def notify(user_id: str | None, type: str, title: str, message: str | None = None,
                  related_type: str | None = None, related_id: str | None = None):
    """Direct port of server/src/utils/notify.js's notify()."""
    if not user_id:
        return
    await notifications.insert_one({
        "_id": new_id(),
        "user_id": user_id,
        "type": type,
        "title": title,
        "message": message,
        "related_type": related_type,
        "related_id": related_id,
        "is_read": False,
        "created_at": now(),
    })


async def notify_many(user_ids: list, **payload):
    for uid in user_ids:
        if uid:
            await notify(uid, **payload)

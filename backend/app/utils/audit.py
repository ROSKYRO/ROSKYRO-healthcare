import logging
from app.db import audit_logs
from app.utils.ids import new_id, now

logger = logging.getLogger("roskyro")


async def log_audit(actor_id: str | None, action: str, entity_type: str | None = None, entity_id: str | None = None, meta: dict | None = None):
    """Audit logging must never break the primary request flow."""
    try:
        await audit_logs.insert_one({
            "_id": new_id(),
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "meta": meta,
            "created_at": now(),
        })
    except Exception as err:  # noqa: BLE001
        logger.error("Audit log failed: %s", err)

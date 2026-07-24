# Split out from plans.py purely to avoid a circular import: auth.py needs
# get_active_pillars (to compute the current user's activePillars), and
# plans.py's require_plan dependency needs get_current_user from auth.py.
# This module has no dependency on auth.py, so both can import it safely.
from app.db import organization_subscriptions, plans as plans_collection

PILLAR_CODES = ["grow", "manage", "connect"]


async def get_active_pillars(org_id: str | None) -> set[str]:
    """Resolve the set of pillars an organization currently has active.
    A 'complete' bundle subscription expands to all three pillars."""
    if not org_id:
        return set()
    cursor = organization_subscriptions.find({"org_id": org_id, "status": "active"})
    pillars: set[str] = set()
    async for sub in cursor:
        plan = await plans_collection.find_one({"_id": sub["plan_code"]})
        if not plan:
            continue
        if plan.get("is_bundle") and plan.get("bundle_pillars"):
            pillars.update(plan["bundle_pillars"])
        elif plan["_id"] in PILLAR_CODES:
            pillars.add(plan["_id"])
    return pillars

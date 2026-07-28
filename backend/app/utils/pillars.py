# Split out from plans.py purely to avoid a circular import: auth.py needs
# get_active_pillars (to compute the current user's activePillars), and
# plans.py's require_plan dependency needs get_current_user from auth.py.
# This module has no dependency on auth.py, so both can import it safely.
from app.db import (
    organization_subscriptions, plans as plans_collection,
    partner_subscriptions,
)

PILLAR_CODES = ["grow", "manage", "connect"]


async def _active_pillars_from(subs_collection, plans_collection_ref, org_id: str | None) -> set[str]:
    if not org_id:
        return set()
    cursor = subs_collection.find({"org_id": org_id, "status": "active"})
    pillars: set[str] = set()
    async for sub in cursor:
        plan = await plans_collection_ref.find_one({"_id": sub["plan_code"]})
        if not plan:
            continue
        if plan.get("is_bundle") and plan.get("bundle_pillars"):
            pillars.update(plan["bundle_pillars"])
        elif plan["_id"] in PILLAR_CODES:
            pillars.add(plan["_id"])
    return pillars


async def get_active_pillars(org_id: str | None) -> set[str]:
    """Resolve the set of pillars a BUSINESS (customer) organization
    currently has active. A 'complete' bundle subscription expands to all
    three pillars."""
    return await _active_pillars_from(organization_subscriptions, plans_collection, org_id)


async def get_active_partner_pillars(org_id: str | None) -> set[str]:
    """Partner-audience mirror of get_active_pillars() above -- reads
    subscription ROWS from the separate partner_subscriptions collection
    (its own subscription records, not the business side's), but resolves
    catalog STRUCTURE (is_bundle/bundle_pillars) from the business `plans`
    collection now, not partner_plans.

    HARDENED (found live on roskyro.in, see routers/partner_plans.py's
    header comment for the full story): this used to read plan.is_bundle/
    bundle_pillars from partner_plans_collection. On a real deployment
    where that collection was never separately populated for every code,
    every lookup here silently returned None ("if not plan: continue"),
    so this function returned an EMPTY set regardless of how many partner
    subscriptions were actually active -- breaking every requires_pillar
    gate (e.g. the "reels" add-on wrongly refusing to activate even with
    GROW active) and the /partner-plans/mine activePillars list. The
    business `plans` collection is guaranteed to have this structure for
    every code, so that's the source of truth for it now."""
    return await _active_pillars_from(partner_subscriptions, plans_collection, org_id)

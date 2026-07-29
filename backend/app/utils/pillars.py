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
    """PERFORMANCE: this is the single hottest function in the backend --
    auth.py calls it on EVERY authenticated request, as a router-wide
    dependency, before any endpoint body starts running.

    It used to issue one find_one per active subscription row inside an
    `async for` over the subscription cursor: a classic 1+N, and every one
    of those N is a full network round-trip to Atlas. A business on the
    "complete" bundle plus the reels add-on paid 3 sequential round-trips
    here on every single request -- roughly 30ms of pure latency added to
    every API call before any real work began, on every page of the app.

    Now it batches the plan lookup into ONE $in query, so the cost is a flat
    2 round-trips regardless of how many subscriptions the org holds. This
    is the same batching pattern already used in routers/plans.py,
    routers/referrals.py and routers/settlements.py.
    """
    if not org_id:
        return set()
    subs = await subs_collection.find({"org_id": org_id, "status": "active"}).to_list(None)
    if not subs:
        return set()
    plan_codes = list({s["plan_code"] for s in subs if s.get("plan_code")})
    if not plan_codes:
        return set()
    plan_docs = await plans_collection_ref.find({"_id": {"$in": plan_codes}}).to_list(None)
    pillars: set[str] = set()
    for plan in plan_docs:
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

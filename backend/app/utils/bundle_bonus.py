"""Shared "buy 2 pillars, get the 3rd free" bundle-bonus logic, and the
matching "GROW-only add-on" (reel making) dependency logic -- used by both
the business-audience subscribe/cancel flow (routers/plans.py) and the
partner-audience one (routers/partner_plans.py), which are otherwise
completely separate collections (plans/organization_subscriptions vs
partner_plans/partner_subscriptions) with their own pricing.

Business rule: activate MANAGE + GROW together -> CONNECT is granted free
as a bonus earning service.
Partner rule: activate GROW + CONNECT together -> MANAGE is granted free.

Both are the exact same shape of rule (two trigger pillars -> one bonus
pillar, free), just with different trigger/bonus pillars and different
collections -- so this is one generic implementation, parametrized per
audience by the caller.
"""
from app.utils.ids import new_id, now, to_out


async def apply_bundle_bonus(subs_collection, org_id: str, trigger_a: str, trigger_b: str, bonus_code: str,
                              activated_by: str, active_pillars_fn) -> dict | None:
    """Call AFTER inserting a new subscription row. If both trigger pillars
    are now active and the bonus pillar isn't already active, grants the
    bonus pillar for free (price_at_purchase=0, is_free_addon=True) and
    returns the new subscription doc. Otherwise returns None."""
    pillars = await active_pillars_fn(org_id)
    if trigger_a not in pillars or trigger_b not in pillars or bonus_code in pillars:
        return None
    already = await subs_collection.find_one({"org_id": org_id, "plan_code": bonus_code, "status": "active"})
    if already:
        return None
    doc = {
        "_id": new_id(), "org_id": org_id, "plan_code": bonus_code, "status": "active",
        "source": "bundle_bonus", "activated_by": activated_by, "billing_cycle": "monthly",
        "price_at_purchase": 0, "started_at": now(), "cancelled_at": None, "is_free_addon": True,
    }
    await subs_collection.insert_one(doc)
    return doc


async def revoke_bundle_bonus_if_broken(subs_collection, org_id: str, trigger_a: str, trigger_b: str, bonus_code: str,
                                         active_pillars_fn) -> dict | None:
    """Call AFTER cancelling a subscription. If the trigger pair no longer
    both hold, cancels the bonus pillar's subscription -- but ONLY if it
    was a free bundle-bonus grant (is_free_addon=True); a bonus pillar the
    business/partner separately paid for in full is never auto-cancelled."""
    pillars = await active_pillars_fn(org_id)
    if trigger_a in pillars and trigger_b in pillars:
        return None
    bonus_sub = await subs_collection.find_one({
        "org_id": org_id, "plan_code": bonus_code, "status": "active", "is_free_addon": True,
    })
    if not bonus_sub:
        return None
    await subs_collection.update_one({"_id": bonus_sub["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": now()}})
    updated = await subs_collection.find_one({"_id": bonus_sub["_id"]})
    return to_out(updated)


async def cascade_cancel_dependent_addons(subs_collection, plans_collection_ref, org_id: str, cancelled_plan_code: str) -> list[str]:
    """Call AFTER cancelling any subscription. An add-on plan (is_addon=True)
    can declare `requires_pillar` -- e.g. the "reels" add-on requires GROW.
    If the just-cancelled plan_code is some active add-on's required
    pillar, that add-on no longer makes sense on its own, so cancel it too.
    Returns the list of plan_codes that were cascade-cancelled."""
    rows = await subs_collection.find({"org_id": org_id, "status": "active"}).to_list(None)
    cancelled = []
    for r in rows:
        plan = await plans_collection_ref.find_one({"_id": r["plan_code"]})
        if plan and plan.get("is_addon") and plan.get("requires_pillar") == cancelled_plan_code:
            await subs_collection.update_one({"_id": r["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": now()}})
            cancelled.append(r["plan_code"])
    return cancelled

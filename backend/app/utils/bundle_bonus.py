"""Bundle-plan and add-on dependency helpers -- used by both the
business-audience subscribe/cancel flow (routers/plans.py) and the
partner-audience one (routers/partner_plans.py), which are otherwise
completely separate collections (plans/organization_subscriptions vs
partner_plans/partner_subscriptions) with their own pricing.

NOTE: this module used to also hold the "buy 2 pillars, get the 3rd free"
bundle-BONUS mechanic (business: MANAGE + GROW active -> CONNECT granted
free; partner: GROW + CONNECT active -> MANAGE granted free), implemented as
apply_bundle_bonus()/revoke_bundle_bonus_if_broken(). That mechanic has been
retired per explicit request (the marketing banners describing it are being
removed site-wide) and the two functions implementing it have been deleted
from this file -- this only stops NEW bonus grants going forward; any
partner/business already granted a free subscription via this rule before
the change keeps it (silently clawing back an already-delivered free
service would be a separate real billing decision, not made here).

The two helpers below are UNRELATED to that retired mechanic (they concern
the explicit "ROSKYRO Complete" bundle PLAN and add-on dependency cleanup,
not the implicit 2-pillar bonus) and remain fully active.
"""
from app.utils.ids import now


async def find_active_bundle_covering_pillar(subs_collection, plans_collection_ref, org_id: str, plan_code: str) -> dict | None:
    """True bundle-check (not just a same-plan-code duplicate check): is
    `plan_code` (an individual pillar, e.g. "grow") already granted for
    free via an active BUNDLE subscription (e.g. "complete", whose
    bundle_pillars includes "grow")? Used to block subscribing to an
    individual pillar that's already covered by an active bundle -- without
    this, a business on "complete" could separately subscribe to "grow" and
    get billed for both the bundle AND the individual pillar at once."""
    active_subs = await subs_collection.find({"org_id": org_id, "status": "active"}).to_list(None)
    bundle_plan_codes = list({s["plan_code"] for s in active_subs if s.get("plan_code")})
    if not bundle_plan_codes:
        return None
    bundle_docs = await plans_collection_ref.find({
        "_id": {"$in": bundle_plan_codes}, "is_bundle": True,
    }).to_list(None)
    for bundle in bundle_docs:
        if plan_code in (bundle.get("bundle_pillars") or []):
            return bundle
    return None


async def cascade_cancel_dependent_addons(subs_collection, plans_collection_ref, org_id: str, cancelled_plan_code: str) -> list[str]:
    """Call AFTER cancelling any subscription. An add-on plan (is_addon=True)
    can declare `requires_pillar` -- e.g. the "reels" add-on requires GROW.
    If the just-cancelled plan_code is some active add-on's required
    pillar, that add-on no longer makes sense on its own, so cancel it too.

    If the cancelled plan is itself a BUNDLE (e.g. "complete", whose
    bundle_pillars includes "grow"), its pillars never appear as an add-on's
    own subscription plan_code -- they only ever existed virtually via the
    bundle. So a bundle cancellation must also match against its expanded
    bundle_pillars, or an add-on that required a bundle-only pillar (e.g.
    "reels", which requires "grow") would stay active and billed forever
    after the bundle granting that pillar is cancelled.

    Also guards against cancelling an add-on that's still legitimately
    covered by ANOTHER active source of its required pillar (e.g. the
    business separately has GROW active on its own in addition to a
    bundle) -- only cascades if the required pillar is no longer active
    for this org at all.

    Returns the list of plan_codes that were cascade-cancelled."""
    cancelled_plan = await plans_collection_ref.find_one({"_id": cancelled_plan_code})
    required_pillar_codes = {cancelled_plan_code}
    if cancelled_plan and cancelled_plan.get("is_bundle") and cancelled_plan.get("bundle_pillars"):
        required_pillar_codes.update(cancelled_plan["bundle_pillars"])

    rows = await subs_collection.find({"org_id": org_id, "status": "active"}).to_list(None)
    cancelled = []
    for r in rows:
        plan = await plans_collection_ref.find_one({"_id": r["plan_code"]})
        if not (plan and plan.get("is_addon") and plan.get("requires_pillar") in required_pillar_codes):
            continue
        # Don't cascade if the required pillar is still active through some
        # OTHER still-active subscription (e.g. the org separately holds
        # that pillar individually, or another still-active bundle grants it).
        still_covered = await _pillar_still_covered(subs_collection, plans_collection_ref, org_id, plan["requires_pillar"], exclude_ids={r["_id"]})
        if still_covered:
            continue
        await subs_collection.update_one({"_id": r["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": now()}})
        cancelled.append(r["plan_code"])
    return cancelled


async def _pillar_still_covered(subs_collection, plans_collection_ref, org_id: str, pillar_code: str, exclude_ids: set) -> bool:
    """Is `pillar_code` still active for this org through any subscription
    OTHER than the ones in `exclude_ids` -- either an individual sub for
    that exact plan_code, or an active bundle whose bundle_pillars include
    it?"""
    active_subs = await subs_collection.find({"org_id": org_id, "status": "active"}).to_list(None)
    remaining = [s for s in active_subs if s["_id"] not in exclude_ids]
    if any(s.get("plan_code") == pillar_code for s in remaining):
        return True
    plan_codes = list({s["plan_code"] for s in remaining if s.get("plan_code")})
    if not plan_codes:
        return False
    bundle_docs = await plans_collection_ref.find({"_id": {"$in": plan_codes}, "is_bundle": True}).to_list(None)
    return any(pillar_code in (b.get("bundle_pillars") or []) for b in bundle_docs)

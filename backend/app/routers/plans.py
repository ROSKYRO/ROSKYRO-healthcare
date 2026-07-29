import math

from fastapi import APIRouter, HTTPException, Depends

from app.db import plans as plans_collection, organization_subscriptions, organizations, users, partner_plans as partner_plans_collection
from app.auth import get_current_user, require_internal, require_roles
from app.utils.plans import get_active_pillars, next_renewal_date
from app.utils.bundle_bonus import (
    cascade_cancel_dependent_addons, find_active_bundle_covering_pillar,
)
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.subscriptions import enforce_single_active
from app.utils.ids import new_id, now, to_out, to_out_many

# Removed per explicit request: the "activate MANAGE + GROW together ->
# Networking Marketing (CONNECT) granted free" bonus is retired -- every
# pillar is now paid for individually, no auto-granted free pillar. This
# ONLY stops NEW bonuses from being granted going forward; any business
# that was already granted a free CONNECT subscription before this change
# keeps it active (removing already-delivered free service from a live
# customer with no notice would be a separate, real billing action, not a
# code fix -- flagged separately, not done here). The mirror-image partner
# rule (GROW + CONNECT -> MANAGE free) is removed the same way in
# partner_plans.py. find_active_bundle_covering_pillar and
# cascade_cancel_dependent_addons are UNRELATED features (the "ROSKYRO
# Complete" bundle-plan double-billing guard, and the "reels" add-on
# dependency cleanup) and are untouched.

router = APIRouter(prefix="/api/plans", tags=["plans"])

EDITABLE_PLAN_FIELDS = ["name", "tagline", "monthly_price", "yearly_price", "description", "best_for", "customer_promise", "features", "badge"]
EDITABLE_PLAN_FIELDS_CAMEL = {
    "name": "name", "tagline": "tagline", "monthlyPrice": "monthly_price", "yearlyPrice": "yearly_price",
    "description": "description", "bestFor": "best_for", "customerPromise": "customer_promise",
    "features": "features", "badge": "badge",
}


def _plan_out(doc: dict) -> dict:
    """Plans use their code (e.g. "grow") as _id, so to_out()'s generic
    _id -> id rename alone isn't enough -- every frontend list/detail view
    (PricingCards, Plans.jsx, PricingManagement.jsx) reads plan.code
    specifically (for React keys, active-plan matching, and the
    subscribe/PATCH request bodies), so it must be present explicitly, not
    just implied by id."""
    item = to_out(doc)
    if item is not None:
        item["code"] = item["id"]
    return item


@router.get("")
@router.get("/")
async def list_plans():
    """Public pricing catalog (used by the marketing pricing page)."""
    rows = await plans_collection.find({}).sort("sort_order", 1).to_list(None)
    return {"plans": [_plan_out(r) for r in rows]}


@router.patch("/{code}", dependencies=[Depends(require_roles("roskyro_admin"))])
async def patch_plan(code: str, body: dict, current_user: dict = Depends(get_current_user)):
    """ROSKYRO super admin only: edit pricing & copy for a pillar or the
    bundle. Nothing else in the app can change plan pricing -- customers
    only ever choose among what's already published here.

    This business catalog is now the SINGLE SOURCE OF TRUTH for pricing
    across both audiences: whenever monthly_price/yearly_price change here,
    the change is propagated into the matching partner_plans doc (same
    code) too, so the "For Partners" pricing tab can never drift from "For
    Businesses" again -- see partner_plans.py's patch_partner_plan(), which
    no longer accepts monthlyPrice/yearlyPrice at all (removed per explicit
    request, since independent partner-side price edits were exactly what
    caused the two catalogs to show different numbers)."""
    updates = {}
    for camel, snake in EDITABLE_PLAN_FIELDS_CAMEL.items():
        if camel in body:
            updates[snake] = body[camel]
        elif snake in body:  # tolerate snake_case too, matching Node's direct field-name PATCH body
            updates[snake] = body[snake]
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields provided.")
    # Fixed: monthly_price/yearly_price were stored completely unvalidated.
    # A non-numeric value saved here doesn't fail at write time -- it sits
    # in the catalog, gets copied into a subscription's price_at_purchase
    # the next time ANY business subscribes to this plan, and only THEN
    # crashes with an unhandled ValueError the first time that business's
    # own GET /plans/mine (my_subscriptions, below) does `float(price or
    # 0)` on it. Same class of gap already fixed for doctors.py/
    # appointments.py/booking_settings.py in earlier rounds -- an
    # admin-side write with no numeric check breaking an unrelated,
    # customer-facing read path later.
    #
    # Round 18 closed three remaining holes in that check:
    #   1. `is not None` meant an explicit JSON null SKIPPED validation and
    #      was written straight through -- the plan then had no price at all,
    #      so `float(price or 0)` downstream silently valued it at ZERO. The
    #      plan quietly became free for every business that subscribed next,
    #      with nothing anywhere reporting an error.
    #   2. There was no non-negativity check, so {"monthlyPrice": -9999} was
    #      accepted and went on to generate negative renewal invoices.
    #   3. float() accepts the strings "NaN"/"Infinity", which then break
    #      JSON serialisation of the catalog for everyone (FastAPI uses
    #      allow_nan=False), including the PUBLIC pricing page.
    price_updates = {}
    for price_field in ("monthly_price", "yearly_price"):
        if price_field in updates:
            if updates[price_field] is None:
                raise HTTPException(status_code=400, detail=f"{price_field} cannot be empty.")
            try:
                value = float(updates[price_field])
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{price_field} must be numeric.")
            if not math.isfinite(value):
                raise HTTPException(status_code=400, detail=f"{price_field} must be a real number.")
            if value < 0:
                raise HTTPException(status_code=400, detail=f"{price_field} cannot be negative.")
            updates[price_field] = value
            price_updates[price_field] = value

    result = await plans_collection.update_one({"_id": code}, {"$set": updates})
    updated = await plans_collection.find_one({"_id": code})
    if not updated:
        raise HTTPException(status_code=404, detail="Unknown plan.")

    # Permanent price sync (per explicit request): propagate into the
    # partner-audience catalog's matching plan doc, if one exists for this
    # code. A no-op (matched_count 0) for a business-only plan code that has
    # no partner-side equivalent -- never raises, since this is a pure
    # side-effect of the business catalog being canonical for pricing.
    if price_updates:
        await partner_plans_collection.update_one({"_id": code}, {"$set": price_updates})

    await log_audit(current_user["id"], "plan.updated", "plan", None, {"code": code, "fields": list(body.keys())})
    return {"plan": _plan_out(updated)}


@router.get("/subscriptions", dependencies=[Depends(require_roles("roskyro_admin"))])
async def all_subscriptions():
    """ROSKYRO super admin only: every org's subscriptions across the
    platform, with a computed next-renewal date per active row, for
    billing follow-up. Cancelled subscriptions show no renewal date since
    nothing is due."""
    # Capped like every other platform-wide admin list (see orgs.py's
    # list_orgs, settlements.py's list_settlements) -- this endpoint has no
    # org/status filter at all, so without a limit it would return every
    # subscription ever created, across every business, forever.
    rows = await organization_subscriptions.find({}).sort("started_at", -1).limit(300).to_list(None)

    # Batch-fetch org + plan ONCE each via $in, instead of 2 find_one calls
    # per subscription row -- same fix as referrals.py/settlements.py/
    # partners.py/orgs.py/tasks.py/approvals.py: a fixed 2 queries total
    # instead of 1 + 2*N.
    org_ids = list({r["org_id"] for r in rows if r.get("org_id")})
    plan_codes = list({r["plan_code"] for r in rows if r.get("plan_code")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}
    plan_docs = await plans_collection.find({"_id": {"$in": plan_codes}}).to_list(None) if plan_codes else []
    plans_by_code = {p["_id"]: p for p in plan_docs}

    subs = []
    for r in rows:
        org = orgs_by_id.get(r.get("org_id"))
        plan = plans_by_code.get(r.get("plan_code"))
        item = to_out(r)
        item["org_name"] = org.get("name") if org else None
        item["plan_name"] = plan.get("name") if plan else None
        item["is_bundle"] = plan.get("is_bundle") if plan else None
        item["renewal_date"] = next_renewal_date(r["started_at"], r["billing_cycle"]) if r["status"] == "active" else None
        subs.append(item)
    subs.sort(key=lambda s: (s["status"] != "active", s.get("org_name") or "", s.get("started_at")), reverse=False)
    return {"subscriptions": subs}


@router.get("/mine")
async def my_subscriptions(current_user: dict = Depends(get_current_user)):
    """The calling customer org's active subscriptions + pillars."""
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Customer accounts only.")

    rows = await organization_subscriptions.find({"org_id": current_user["orgId"]}).sort("started_at", -1).to_list(None)

    # Batch-fetch every referenced plan ONCE via $in instead of a find_one
    # per subscription row -- same 1 + N -> fixed-2-queries fix already
    # applied to GET /subscriptions above.
    plan_codes = list({r["plan_code"] for r in rows if r.get("plan_code")})
    plan_docs = await plans_collection.find({"_id": {"$in": plan_codes}}).to_list(None) if plan_codes else []
    plans_by_code = {p["_id"]: p for p in plan_docs}

    out = []
    for r in rows:
        plan = plans_by_code.get(r["plan_code"])
        item = to_out(r)
        item["name"] = plan.get("name") if plan else None
        item["monthly_price"] = plan.get("monthly_price") if plan else None
        item["yearly_price"] = plan.get("yearly_price") if plan else None
        item["is_bundle"] = plan.get("is_bundle") if plan else None
        out.append(item)

    active = [r for r in out if r["status"] == "active"]
    # Reuse the pillar set auth.py already computed for this request rather
    # than recomputing it with another round of database queries. The React
    # app calls /auth/me and /plans/mine back-to-back on every page load, so
    # this was running the same work three times per boot.
    pillars = current_user.get("activePillars")
    if pillars is None:
        pillars = await get_active_pillars(current_user["orgId"])

    monthly_total = 0.0
    for r in active:
        price = r.get("price_at_purchase")
        if price is None:
            price = r.get("monthly_price")
        price = float(price or 0)
        monthly_total += price / 12 if r.get("billing_cycle") == "yearly" else price

    return {"subscriptions": out, "activeSubscriptions": active, "activePillars": list(pillars), "monthlyTotal": monthly_total}


@router.get("/org/{org_id}", dependencies=[Depends(require_internal)])
async def org_subscriptions(org_id: str):
    rows = await organization_subscriptions.find({"org_id": org_id}).sort("started_at", -1).to_list(None)

    plan_codes = list({r["plan_code"] for r in rows if r.get("plan_code")})
    plan_docs = await plans_collection.find({"_id": {"$in": plan_codes}}).to_list(None) if plan_codes else []
    plans_by_code = {p["_id"]: p for p in plan_docs}

    out = []
    for r in rows:
        plan = plans_by_code.get(r["plan_code"])
        item = to_out(r)
        item["name"] = plan.get("name") if plan else None
        item["monthly_price"] = plan.get("monthly_price") if plan else None
        item["is_bundle"] = plan.get("is_bundle") if plan else None
        out.append(item)
    pillars = await get_active_pillars(org_id)
    return {"subscriptions": out, "activePillars": list(pillars)}


@router.post("/subscribe", status_code=201)
async def subscribe(body: dict, current_user: dict = Depends(get_current_user)):
    """Self-serve activate a plan for your own org (simulates
    checkout/payment -- no real billing gateway in v1). Also usable by
    internal staff to assign a plan to any org via { orgId }."""
    plan_code = body.get("planCode")
    billing_cycle = "yearly" if body.get("billingCycle") == "yearly" else "monthly"
    target_org_id = body.get("orgId") if current_user["appShell"] == "internal" and body.get("orgId") else current_user.get("orgId")

    if current_user["appShell"] == "customer" and current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the business owner can change the ROSKYRO subscription.")
    if current_user["appShell"] == "partner":
        raise HTTPException(status_code=403, detail="Partner accounts do not hold pillar subscriptions.")
    if not target_org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")
    if not plan_code:
        raise HTTPException(status_code=400, detail="planCode is required.")

    plan = await plans_collection.find_one({"_id": plan_code})
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan.")
    price_at_purchase = plan.get("yearly_price") if billing_cycle == "yearly" else plan.get("monthly_price")

    # Add-on plans (e.g. "reels" -- Reel Making) only make sense alongside
    # the pillar they extend. requires_pillar is set on the plan doc itself
    # so this check works for ANY future add-on, not just reels.
    if plan.get("is_addon") and plan.get("requires_pillar"):
        active_now = await get_active_pillars(target_org_id)
        if plan["requires_pillar"] not in active_now:
            raise HTTPException(
                status_code=400,
                detail=f"{plan['requires_pillar'].upper()} must be active before adding {plan['name']}.",
            )

    if plan.get("is_bundle"):
        # Fixed double-billing bug: the individual-pillar branch below has
        # had a same-plan duplicate guard for a long time, but the BUNDLE
        # branch had none at all. Subscribing to "complete" twice (e.g. an
        # owner switching monthly -> yearly, or a double-clicked button)
        # left BOTH rows active and billed both -- ₹24,999/mo AND
        # ₹2,39,990/yr on the same business, forever, with two renewal
        # invoices raised every period.
        existing_bundle = await organization_subscriptions.find_one(
            {"org_id": target_org_id, "plan_code": plan_code, "status": "active"}
        )
        if existing_bundle:
            raise HTTPException(status_code=409, detail=f"{plan['name']} is already active for this business.")
        # If subscribing to the bundle, cancel any individual pillar
        # subscriptions they're replacing (avoid double-billing in the demo).
        # Add-ons (e.g. a paid-for reel-making subscription) are NOT swept
        # up here -- the bundle already grants GROW, so an active add-on
        # that requires GROW stays valid and shouldn't be silently cancelled.
        #
        # Also fixed: the $nin list hardcoded the literal "complete" instead
        # of this plan's own code, so any bundle other than "complete" would
        # have swept away a *different* already-active bundle's row silently
        # rather than being caught by the 409 above.
        addon_codes = [p["_id"] async for p in plans_collection.find({"is_addon": True})]
        await organization_subscriptions.update_many(
            {"org_id": target_org_id, "status": "active", "plan_code": {"$nin": [plan_code] + addon_codes}},
            {"$set": {"status": "cancelled", "cancelled_at": now()}},
        )
    else:
        # Subscribing to an individual pillar while the bundle is active is a
        # no-op (bundle already grants it) -- guard against duplicate rows.
        existing = await organization_subscriptions.find_one({"org_id": target_org_id, "plan_code": plan_code, "status": "active"})
        if existing:
            raise HTTPException(status_code=409, detail=f"{plan['name']} is already active for this business.")
        # Fixed double-billing bug: the check above only caught a duplicate
        # of the SAME plan_code -- it never checked whether an active BUNDLE
        # (e.g. "complete") already covers this pillar. Without this, a
        # business on "complete" (₹24,999/mo, includes grow+manage+connect)
        # could separately subscribe to "grow" (₹14,999/mo) and get billed
        # for both at once, since no "grow" row existed yet to trip the
        # check above.
        covering_bundle = await find_active_bundle_covering_pillar(organization_subscriptions, plans_collection, target_org_id, plan_code)
        if covering_bundle:
            raise HTTPException(
                status_code=409,
                detail=f"{plan['name']} is already included in your active {covering_bundle['name']} bundle.",
            )

    doc = {
        "_id": new_id(), "org_id": target_org_id, "plan_code": plan_code, "status": "active",
        "source": "admin_assigned" if current_user["appShell"] == "internal" else "self_upgrade",
        "activated_by": current_user["id"], "billing_cycle": billing_cycle,
        "price_at_purchase": price_at_purchase, "started_at": now(), "cancelled_at": None,
    }
    await organization_subscriptions.insert_one(doc)
    # Close the check-then-insert race that both guards above are subject to
    # (see app/utils/subscriptions.py). A double-clicked "Activate" button
    # used to create two active rows for the same plan and bill the business
    # twice every renewal, forever.
    if not await enforce_single_active(organization_subscriptions, target_org_id, plan_code, doc["_id"]):
        raise HTTPException(status_code=409, detail=f"{plan['name']} is already active for this business.")

    owner = await users.find_one({"org_id": target_org_id, "role": "owner"})
    if owner and owner["_id"] != current_user["id"]:
        amount_label = f"₹{price_at_purchase}/year" if billing_cycle == "yearly" else f"₹{price_at_purchase}/month"
        await notify(owner["_id"], "plan_activated", f"{plan['name']} is now active", amount_label, "plan", None)

    await log_audit(current_user["id"], "plan.subscribed", "organization", target_org_id, {"planCode": plan_code, "billingCycle": billing_cycle})
    return {"subscription": to_out(doc)}


@router.post("/cancel")
async def cancel(body: dict, current_user: dict = Depends(get_current_user)):
    plan_code = body.get("planCode")
    if current_user["appShell"] == "customer" and current_user["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the business owner can change the ROSKYRO subscription.")
    org_id = body.get("orgId") if current_user["appShell"] == "internal" and body.get("orgId") else current_user.get("orgId")

    existing = await organization_subscriptions.find_one({"org_id": org_id, "plan_code": plan_code, "status": "active"})
    if not existing:
        raise HTTPException(status_code=404, detail="No active subscription found for that plan.")

    await organization_subscriptions.update_one({"_id": existing["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": now()}})
    updated = await organization_subscriptions.find_one({"_id": existing["_id"]})
    await log_audit(current_user["id"], "plan.cancelled", "organization", org_id, {"planCode": plan_code})

    # Any add-on that required THIS specific pillar (e.g. "reels" requires
    # GROW) no longer stands on its own -- cancel it too. (The bundle-bonus
    # auto-revoke that used to run here was removed along with the bonus
    # feature itself -- see this file's header comment.)
    cascaded = await cascade_cancel_dependent_addons(organization_subscriptions, plans_collection, org_id, plan_code)

    return {"subscription": to_out(updated), "addonsCancelled": cascaded}

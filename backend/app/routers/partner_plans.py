from fastapi import APIRouter, HTTPException, Depends

from app.db import (
    partner_plans as partner_plans_collection, partner_subscriptions, organizations, users,
    plans as business_plans_collection,
)
from app.auth import get_current_user, require_roles
from app.utils.pillars import get_active_partner_pillars
from app.utils.plans import next_renewal_date
from app.utils.bundle_bonus import (
    cascade_cancel_dependent_addons, find_active_bundle_covering_pillar,
)
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.subscriptions import enforce_single_active
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(prefix="/api/partner-plans", tags=["partner-plans"])

# Partner-audience mirror of routers/plans.py -- same services (GROW /
# MANAGE / CONNECT / a bundle, plus the "reels" add-on), its
# own subscriptions collection (partner_subscriptions, separate from the
# business side's organization_subscriptions), but pricing is NOT separate
# -- see plans.py's patch_plan(), which now keeps this catalog's
# monthly_price/yearly_price in sync with the business catalog's, so the
# two audiences always show identical prices for the same service.
#
# Removed per explicit request: the "activate GROW + CONNECT
# (CONNECT) together -> MANAGE granted free" bonus (the mirror image of
# plans.py's business-side rule) is retired -- see plans.py's header
# comment for the full reasoning (only stops NEW bonuses; any partner
# already granted a free MANAGE subscription before this change keeps it).
#
# HARDENED (found live on roskyro.in): the "For Partners" pricing tab was
# rendering completely blank in production, and subscribing to a partner
# plan would 404 as "Unknown plan." -- both traced to every read in this
# file (list_partner_plans, subscribe_partner, the bundle/addon helpers,
# the admin subscriptions view, my_partner_subscriptions) querying ONLY
# the partner_plans collection directly. In the demo/mock DB that
# collection is always deep-copied from the business catalog at seed time
# (see seed.py) so this never showed up locally, but on a real deployment
# where partner_plans was never separately populated for every code, those
# lookups silently returned nothing. Fixed by making the business `plans`
# collection the actual fallback data source everywhere in this file, not
# just the price-sync target on write -- see _effective_partner_plans_map()
# below. Every catalog read here now goes through it, so a partner_plans
# collection that's partially or entirely empty still produces a complete,
# correctly-priced catalog identical to the business tab, and subscribing
# to any valid business-catalog code always works.

# NOTE: monthlyPrice/yearlyPrice deliberately excluded (removed per explicit
# request) -- pricing is no longer independently editable on this catalog
# at all. plans.py's patch_plan() is the single source of truth for pricing
# and propagates monthly_price/yearly_price into this collection's matching
# doc on every business-side price edit, so the two audiences can never
# show different prices for the same service again.
EDITABLE_PLAN_FIELDS_CAMEL = {
    "name": "name", "tagline": "tagline",
    "description": "description", "bestFor": "best_for", "customerPromise": "customer_promise",
    "features": "features", "badge": "badge",
}

# Copy fields a partner_plans doc is allowed to override on top of the
# business catalog's base doc -- everything else (importantly, pricing) is
# always taken from the business plan, never from partner_plans.
_COPY_FIELDS = ("name", "tagline", "description", "best_for", "customer_promise", "features", "badge")


async def _effective_partner_plans_map(codes: list | None = None) -> dict:
    """code -> merged effective partner-audience plan doc, for either every
    business plan (codes=None) or just the given codes. The business `plans`
    collection is the base for EVERY field (guaranteed to exist and be
    correctly priced); a partner_plans doc for that code, if one exists,
    only overrides the copy fields in _COPY_FIELDS when they're actually
    set (non-None/non-empty) -- monthly_price/yearly_price are always
    re-taken from the business plan afterward regardless of what a legacy
    partner_plans doc might still contain, so this can never regress the
    price-sync guarantee even if an old partner_plans row has a stale price.
    Returns {} if none of the requested codes exist on the business side."""
    query = {"_id": {"$in": list(codes)}} if codes is not None else {}
    business_rows = await business_plans_collection.find(query).sort("sort_order", 1).to_list(None)
    if not business_rows:
        return {}
    partner_rows = await partner_plans_collection.find(
        {"_id": {"$in": [b["_id"] for b in business_rows]}}
    ).to_list(None)
    partner_by_code = {r["_id"]: r for r in partner_rows}

    merged_map = {}
    for business_plan in business_rows:
        code = business_plan["_id"]
        merged = dict(business_plan)
        partner_doc = partner_by_code.get(code)
        if partner_doc:
            for field in _COPY_FIELDS:
                if partner_doc.get(field) not in (None, "", []):
                    merged[field] = partner_doc[field]
        merged["monthly_price"] = business_plan["monthly_price"]
        merged["yearly_price"] = business_plan["yearly_price"]
        merged["_id"] = code
        merged_map[code] = merged
    return merged_map


def _plan_out(doc: dict) -> dict:
    item = to_out(doc)
    if item is not None:
        item["code"] = item["id"]
    return item


def _require_partner(current_user: dict):
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner accounts only.")
    if current_user["role"] != "partner_admin":
        raise HTTPException(status_code=403, detail="Only the partner admin can change the ROSKYRO subscription.")


@router.get("")
@router.get("/")
async def list_partner_plans():
    """Public partner-audience pricing catalog (used by the marketing
    Pricing/Services pages' 'For Partners' tab, and the in-app partner
    Plans page). Always derived from the business catalog (see
    _effective_partner_plans_map) so this never renders an empty/partial
    list even if partner_plans hasn't been separately populated."""
    merged_map = await _effective_partner_plans_map()
    return {"plans": [_plan_out(r) for r in merged_map.values()]}


@router.patch("/{code}", dependencies=[Depends(require_roles("roskyro_admin"))])
async def patch_partner_plan(code: str, body: dict, current_user: dict = Depends(get_current_user)):
    """ROSKYRO super admin only -- same editing rules as PATCH /plans/{code}
    for copy/features, against the partner catalog. Pricing is NOT editable
    here at all (see EDITABLE_PLAN_FIELDS_CAMEL's note above): even if a
    caller sends monthlyPrice/yearlyPrice in the body, those keys are simply
    not in EDITABLE_PLAN_FIELDS_CAMEL, so they're silently ignored here --
    prices only ever change via plans.py's patch_plan(), which propagates
    into this collection automatically.

    Existence is checked against the BUSINESS catalog, not this collection
    -- partner_plans may legitimately have no row yet for a perfectly valid
    code (see _effective_partner_plans_map), so a missing partner_plans
    document must not 404 a real plan. upsert=True below creates that row
    (with just the edited copy fields) the first time an admin edits it."""
    updates = {}
    for camel, snake in EDITABLE_PLAN_FIELDS_CAMEL.items():
        if camel in body:
            updates[snake] = body[camel]
        elif snake in body:
            updates[snake] = body[snake]
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields provided.")

    business_plan = await business_plans_collection.find_one({"_id": code})
    if not business_plan:
        raise HTTPException(status_code=404, detail="Unknown plan.")

    await partner_plans_collection.update_one({"_id": code}, {"$set": updates}, upsert=True)

    await log_audit(current_user["id"], "partner_plan.updated", "partner_plan", None, {"code": code, "fields": list(body.keys())})
    merged = (await _effective_partner_plans_map([code])).get(code)
    return {"plan": _plan_out(merged)}


@router.get("/subscriptions", dependencies=[Depends(require_roles("roskyro_admin"))])
async def all_partner_subscriptions():
    """ROSKYRO super admin only -- every partner org's subscriptions
    platform-wide, mirroring GET /plans/subscriptions."""
    rows = await partner_subscriptions.find({}).sort("started_at", -1).limit(300).to_list(None)

    org_ids = list({r["org_id"] for r in rows if r.get("org_id")})
    plan_codes = list({r["plan_code"] for r in rows if r.get("plan_code")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}
    plans_by_code = await _effective_partner_plans_map(plan_codes) if plan_codes else {}

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
async def my_partner_subscriptions(current_user: dict = Depends(get_current_user)):
    """The calling partner org's own active subscriptions + pillars."""
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner accounts only.")

    rows = await partner_subscriptions.find({"org_id": current_user["orgId"]}).sort("started_at", -1).to_list(None)

    # Batch-fetch every referenced plan ONCE via $in instead of a find_one
    # per subscription row -- mirrors the same fix in routers/plans.py's
    # my_subscriptions. Goes through the business-catalog-backed merge so a
    # subscription never shows a null name/price just because partner_plans
    # itself has no row for that code.
    plan_codes = list({r["plan_code"] for r in rows if r.get("plan_code")})
    plans_by_code = await _effective_partner_plans_map(plan_codes) if plan_codes else {}

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
    # Reuse the pillar set auth.py already computed for this request instead
    # of recomputing it with a fresh round of queries (the React app hits
    # /auth/me and /partner-plans/mine back-to-back on every page load).
    pillars = current_user.get("activePillars")
    if pillars is None:
        pillars = await get_active_partner_pillars(current_user["orgId"])

    monthly_total = 0.0
    for r in active:
        price = r.get("price_at_purchase")
        if price is None:
            price = r.get("monthly_price")
        price = float(price or 0)
        monthly_total += price / 12 if r.get("billing_cycle") == "yearly" else price

    return {"subscriptions": out, "activeSubscriptions": active, "activePillars": list(pillars), "monthlyTotal": monthly_total}


@router.post("/subscribe", status_code=201)
async def subscribe_partner(body: dict, current_user: dict = Depends(get_current_user)):
    """Claim a partner-priced plan for your own partner org via self-serve
    UPI payment.

    Round 23: no longer activates instantly (mirrors routers/plans.py's
    business-side subscribe() -- see that function's docstring for the full
    reasoning). Created with status "pending_payment"; the pillar stays
    LOCKED (get_active_partner_pillars only ever counts status=="active"
    rows) until a roskyro_admin reviews the UPI payment and calls
    POST /{id}/confirm-payment."""
    _require_partner(current_user)
    plan_code = body.get("planCode")
    billing_cycle = "yearly" if body.get("billingCycle") == "yearly" else "monthly"
    payment_reference = (body.get("paymentReference") or "").strip() or None
    org_id = current_user["orgId"]

    if not plan_code:
        raise HTTPException(status_code=400, detail="planCode is required.")

    plan = (await _effective_partner_plans_map([plan_code])).get(plan_code)
    if not plan:
        raise HTTPException(status_code=404, detail="Unknown plan.")
    price_at_purchase = plan.get("yearly_price") if billing_cycle == "yearly" else plan.get("monthly_price")

    if plan.get("is_addon") and plan.get("requires_pillar"):
        active_now = await get_active_partner_pillars(org_id)
        if plan["requires_pillar"] not in active_now:
            raise HTTPException(
                status_code=400,
                detail=f"{plan['requires_pillar'].upper()} must be active before adding {plan['name']}.",
            )

    if plan.get("is_bundle"):
        # Same double-billing fix as routers/plans.py's subscribe: the bundle
        # branch had no duplicate guard at all (only the individual-pillar
        # branch below did), so re-subscribing to the bundle -- switching
        # monthly to yearly, or just a double-clicked "Activate" -- left BOTH
        # rows active and raised two renewal invoices every period. Round 23:
        # also blocks a second claim while an earlier one is still pending.
        existing_bundle = await partner_subscriptions.find_one(
            {"org_id": org_id, "plan_code": plan_code, "status": {"$in": ["active", "pending_payment"]}}
        )
        if existing_bundle:
            detail = (f"{plan['name']} is already active for this partner." if existing_bundle["status"] == "active"
                      else f"A request to activate {plan['name']} is already awaiting ROSKYRO confirmation.")
            raise HTTPException(status_code=409, detail=detail)
        # Catalog STRUCTURE (is_addon/is_bundle/bundle_pillars/requires_pillar)
        # is always read from the business collection now, not partner_plans
        # -- see this file's header comment -- since that's guaranteed to be
        # fully populated, unlike partner_plans in a fresh deployment.
        #
        # The $nin list also used to hardcode the literal "complete" rather
        # than this plan's own code, so a future second bundle would have
        # silently cancelled an active "complete" row instead of surfacing
        # the 409 above.
        #
        # Round 23: the actual cancel-superseded-plans sweep is deferred to
        # confirm_partner_payment() below -- see routers/plans.py's
        # confirm_payment() docstring for why (no coverage gap while a
        # claim awaits confirmation).
    else:
        existing = await partner_subscriptions.find_one(
            {"org_id": org_id, "plan_code": plan_code, "status": {"$in": ["active", "pending_payment"]}}
        )
        if existing:
            detail = (f"{plan['name']} is already active for this partner." if existing["status"] == "active"
                      else f"A request to activate {plan['name']} is already awaiting ROSKYRO confirmation.")
            raise HTTPException(status_code=409, detail=detail)
        # Same double-billing fix as routers/plans.py's subscribe -- block
        # subscribing to an individual pillar already covered by an active
        # bundle, not just an exact-plan_code duplicate.
        covering_bundle = await find_active_bundle_covering_pillar(partner_subscriptions, business_plans_collection, org_id, plan_code)
        if covering_bundle:
            raise HTTPException(
                status_code=409,
                detail=f"{plan['name']} is already included in your active {covering_bundle['name']} bundle.",
            )

    doc = {
        "_id": new_id(), "org_id": org_id, "plan_code": plan_code, "status": "pending_payment",
        "source": "self_upgrade", "activated_by": current_user["id"], "billing_cycle": billing_cycle,
        "price_at_purchase": price_at_purchase, "started_at": None,
        "requested_at": now(), "payment_reference": payment_reference, "confirmed_by": None,
        "cancelled_at": None,
    }
    await partner_subscriptions.insert_one(doc)

    await log_audit(current_user["id"], "partner_plan.payment_submitted", "organization", org_id, {"planCode": plan_code, "billingCycle": billing_cycle})
    return {"subscription": to_out(doc)}


@router.post("/{subscription_id}/confirm-payment", dependencies=[Depends(require_roles("roskyro_admin"))])
async def confirm_partner_payment(subscription_id: str, current_user: dict = Depends(get_current_user)):
    """ROSKYRO super admin only: confirm a partner's self-serve UPI payment
    claim was actually received -- mirrors routers/plans.py's
    confirm_payment() for the business audience. See that function's
    docstring for the full reasoning, including why a bundle's replaced-plan
    cleanup happens here rather than at claim time."""
    sub = await partner_subscriptions.find_one({"_id": subscription_id})
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription request not found.")
    if sub["status"] != "pending_payment":
        raise HTTPException(status_code=400, detail=f"This request is already {sub['status']}, nothing to confirm.")

    plan = (await _effective_partner_plans_map([sub["plan_code"]])).get(sub["plan_code"])
    if plan and plan.get("is_addon") and plan.get("requires_pillar"):
        active_now = await get_active_partner_pillars(sub["org_id"])
        if plan["requires_pillar"] not in active_now:
            raise HTTPException(
                status_code=400,
                detail=f"{plan['requires_pillar'].upper()} is no longer active on this partner -- cannot confirm {plan.get('name', sub['plan_code'])} until it is.",
            )

    await partner_subscriptions.update_one({"_id": subscription_id}, {"$set": {
        "status": "active", "started_at": now(), "confirmed_by": current_user["id"],
    }})

    if plan and plan.get("is_bundle"):
        addon_codes = [p["_id"] async for p in business_plans_collection.find({"is_addon": True})]
        await partner_subscriptions.update_many(
            {"org_id": sub["org_id"], "status": "active", "plan_code": {"$nin": [sub["plan_code"]] + addon_codes}, "_id": {"$ne": subscription_id}},
            {"$set": {"status": "cancelled", "cancelled_at": now()}},
        )

    if not await enforce_single_active(partner_subscriptions, sub["org_id"], sub["plan_code"], subscription_id):
        raise HTTPException(status_code=409, detail="This plan was already confirmed active for this partner by another request.")

    updated = await partner_subscriptions.find_one({"_id": subscription_id})
    partner_admin = await users.find_one({"org_id": sub["org_id"], "role": "partner_admin"})
    if partner_admin:
        price = updated.get("price_at_purchase")
        amount_label = f"₹{price}/year" if updated.get("billing_cycle") == "yearly" else f"₹{price}/month"
        await notify(partner_admin["_id"], "plan_activated", f"{plan['name'] if plan else sub['plan_code']} is now active", amount_label, "plan", None)

    await log_audit(current_user["id"], "partner_plan.payment_confirmed", "organization", sub["org_id"], {"planCode": sub["plan_code"], "subscriptionId": subscription_id})
    return {"subscription": to_out(updated)}


@router.post("/{subscription_id}/reject-payment", dependencies=[Depends(require_roles("roskyro_admin"))])
async def reject_partner_payment(subscription_id: str, body: dict | None = None, current_user: dict = Depends(get_current_user)):
    """ROSKYRO super admin only -- mirrors routers/plans.py's
    reject_payment() for the partner audience."""
    sub = await partner_subscriptions.find_one({"_id": subscription_id})
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription request not found.")
    if sub["status"] != "pending_payment":
        raise HTTPException(status_code=400, detail=f"This request is already {sub['status']}, nothing to reject.")

    reason = ((body or {}).get("reason") or "").strip() or None
    await partner_subscriptions.update_one({"_id": subscription_id}, {"$set": {
        "status": "payment_rejected", "confirmed_by": current_user["id"], "rejected_at": now(), "rejection_reason": reason,
    }})
    updated = await partner_subscriptions.find_one({"_id": subscription_id})

    plan = (await _effective_partner_plans_map([sub["plan_code"]])).get(sub["plan_code"])
    partner_admin = await users.find_one({"org_id": sub["org_id"], "role": "partner_admin"})
    if partner_admin:
        await notify(
            partner_admin["_id"], "plan_payment_rejected",
            f"Payment not confirmed for {plan['name'] if plan else sub['plan_code']}",
            reason or "ROSKYRO could not verify this payment -- please re-check and submit again from Plans & Billing.",
            "plan", None,
        )

    await log_audit(current_user["id"], "partner_plan.payment_rejected", "organization", sub["org_id"], {"planCode": sub["plan_code"], "subscriptionId": subscription_id, "reason": reason})
    return {"subscription": to_out(updated)}


@router.post("/cancel")
async def cancel_partner(body: dict, current_user: dict = Depends(get_current_user)):
    _require_partner(current_user)
    plan_code = body.get("planCode")
    org_id = current_user["orgId"]

    existing = await partner_subscriptions.find_one({"org_id": org_id, "plan_code": plan_code, "status": "active"})
    if not existing:
        # Round 23: a still-pending (unconfirmed) claim can also be
        # withdrawn -- mirrors routers/plans.py's cancel().
        pending = await partner_subscriptions.find_one({"org_id": org_id, "plan_code": plan_code, "status": "pending_payment"})
        if pending:
            await partner_subscriptions.update_one({"_id": pending["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": now()}})
            updated = await partner_subscriptions.find_one({"_id": pending["_id"]})
            await log_audit(current_user["id"], "partner_plan.payment_withdrawn", "organization", org_id, {"planCode": plan_code})
            return {"subscription": to_out(updated), "addonsCancelled": []}
        raise HTTPException(status_code=404, detail="No active subscription found for that plan.")

    await partner_subscriptions.update_one({"_id": existing["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": now()}})
    updated = await partner_subscriptions.find_one({"_id": existing["_id"]})
    await log_audit(current_user["id"], "partner_plan.cancelled", "organization", org_id, {"planCode": plan_code})

    cascaded = await cascade_cancel_dependent_addons(partner_subscriptions, business_plans_collection, org_id, plan_code)

    return {"subscription": to_out(updated), "addonsCancelled": cascaded}

from fastapi import APIRouter, HTTPException, Depends

from app.db import partner_plans as partner_plans_collection, partner_subscriptions, organizations, users
from app.auth import get_current_user, require_roles
from app.utils.pillars import get_active_partner_pillars
from app.utils.plans import next_renewal_date
from app.utils.bundle_bonus import apply_bundle_bonus, revoke_bundle_bonus_if_broken, cascade_cancel_dependent_addons
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(prefix="/api/partner-plans", tags=["partner-plans"])

# Partner-audience mirror of routers/plans.py -- same services (GROW /
# MANAGE / Networking Marketing / a bundle, plus the "reels" add-on), but
# its own pricing catalog (partner_plans/partner_subscriptions, kept
# entirely separate from the business ones in plans/organization_subscriptions).
#
# Partner rule: activate GROW + Networking Marketing (CONNECT) together ->
# MANAGE is granted for free (the mirror image of the business rule, which
# is MANAGE + GROW -> CONNECT free). See app/utils/bundle_bonus.py.
PARTNER_BONUS_TRIGGER_A = "grow"
PARTNER_BONUS_TRIGGER_B = "connect"
PARTNER_BONUS_CODE = "manage"

EDITABLE_PLAN_FIELDS_CAMEL = {
    "name": "name", "tagline": "tagline", "monthlyPrice": "monthly_price", "yearlyPrice": "yearly_price",
    "description": "description", "bestFor": "best_for", "customerPromise": "customer_promise",
    "features": "features", "badge": "badge",
}


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
    Plans page)."""
    rows = await partner_plans_collection.find({}).sort("sort_order", 1).to_list(None)
    return {"plans": [_plan_out(r) for r in rows]}


@router.patch("/{code}", dependencies=[Depends(require_roles("roskyro_admin"))])
async def patch_partner_plan(code: str, body: dict, current_user: dict = Depends(get_current_user)):
    """ROSKYRO super admin only -- same editing rules as PATCH /plans/{code},
    just against the partner catalog."""
    updates = {}
    for camel, snake in EDITABLE_PLAN_FIELDS_CAMEL.items():
        if camel in body:
            updates[snake] = body[camel]
        elif snake in body:
            updates[snake] = body[snake]
    if not updates:
        raise HTTPException(status_code=400, detail="No editable fields provided.")

    await partner_plans_collection.update_one({"_id": code}, {"$set": updates})
    updated = await partner_plans_collection.find_one({"_id": code})
    if not updated:
        raise HTTPException(status_code=404, detail="Unknown plan.")

    await log_audit(current_user["id"], "partner_plan.updated", "partner_plan", None, {"code": code, "fields": list(body.keys())})
    return {"plan": _plan_out(updated)}


@router.get("/subscriptions", dependencies=[Depends(require_roles("roskyro_admin"))])
async def all_partner_subscriptions():
    """ROSKYRO super admin only -- every partner org's subscriptions
    platform-wide, mirroring GET /plans/subscriptions."""
    rows = await partner_subscriptions.find({}).sort("started_at", -1).limit(300).to_list(None)

    org_ids = list({r["org_id"] for r in rows if r.get("org_id")})
    plan_codes = list({r["plan_code"] for r in rows if r.get("plan_code")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}
    plan_docs = await partner_plans_collection.find({"_id": {"$in": plan_codes}}).to_list(None) if plan_codes else []
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
async def my_partner_subscriptions(current_user: dict = Depends(get_current_user)):
    """The calling partner org's own active subscriptions + pillars."""
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner accounts only.")

    rows = await partner_subscriptions.find({"org_id": current_user["orgId"]}).sort("started_at", -1).to_list(None)

    # Batch-fetch every referenced plan ONCE via $in instead of a find_one
    # per subscription row -- mirrors the same fix in routers/plans.py's
    # my_subscriptions.
    plan_codes = list({r["plan_code"] for r in rows if r.get("plan_code")})
    plan_docs = await partner_plans_collection.find({"_id": {"$in": plan_codes}}).to_list(None) if plan_codes else []
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
    """Self-serve activate a partner-priced plan for your own partner org
    (simulates checkout/payment -- no real billing gateway in v1)."""
    _require_partner(current_user)
    plan_code = body.get("planCode")
    billing_cycle = "yearly" if body.get("billingCycle") == "yearly" else "monthly"
    org_id = current_user["orgId"]

    if not plan_code:
        raise HTTPException(status_code=400, detail="planCode is required.")

    plan = await partner_plans_collection.find_one({"_id": plan_code})
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
        addon_codes = [p["_id"] async for p in partner_plans_collection.find({"is_addon": True})]
        await partner_subscriptions.update_many(
            {"org_id": org_id, "status": "active", "plan_code": {"$nin": ["complete"] + addon_codes}},
            {"$set": {"status": "cancelled", "cancelled_at": now()}},
        )
    else:
        existing = await partner_subscriptions.find_one({"org_id": org_id, "plan_code": plan_code, "status": "active"})
        if existing:
            raise HTTPException(status_code=409, detail=f"{plan['name']} is already active for this partner.")

    doc = {
        "_id": new_id(), "org_id": org_id, "plan_code": plan_code, "status": "active",
        "source": "self_upgrade", "activated_by": current_user["id"], "billing_cycle": billing_cycle,
        "price_at_purchase": price_at_purchase, "started_at": now(), "cancelled_at": None,
    }
    await partner_subscriptions.insert_one(doc)

    bonus_doc = await apply_bundle_bonus(
        partner_subscriptions, org_id,
        PARTNER_BONUS_TRIGGER_A, PARTNER_BONUS_TRIGGER_B, PARTNER_BONUS_CODE,
        current_user["id"], get_active_partner_pillars,
    )

    partner_admin = await users.find_one({"org_id": org_id, "role": "partner_admin"})
    if partner_admin and partner_admin["_id"] != current_user["id"]:
        amount_label = f"₹{price_at_purchase}/year" if billing_cycle == "yearly" else f"₹{price_at_purchase}/month"
        await notify(partner_admin["_id"], "plan_activated", f"{plan['name']} is now active", amount_label, "plan", None)
    if bonus_doc and partner_admin:
        await notify(partner_admin["_id"], "plan_activated", "MANAGE is now active — free bonus", "₹0/month (GROW + Networking Marketing bonus)", "plan", None)

    await log_audit(current_user["id"], "partner_plan.subscribed", "organization", org_id, {"planCode": plan_code, "billingCycle": billing_cycle})
    if bonus_doc:
        await log_audit(current_user["id"], "partner_plan.bundle_bonus_granted", "organization", org_id, {"planCode": PARTNER_BONUS_CODE})
    return {"subscription": to_out(doc), "bonusGranted": to_out(bonus_doc) if bonus_doc else None}


@router.post("/cancel")
async def cancel_partner(body: dict, current_user: dict = Depends(get_current_user)):
    _require_partner(current_user)
    plan_code = body.get("planCode")
    org_id = current_user["orgId"]

    existing = await partner_subscriptions.find_one({"org_id": org_id, "plan_code": plan_code, "status": "active"})
    if not existing:
        raise HTTPException(status_code=404, detail="No active subscription found for that plan.")

    await partner_subscriptions.update_one({"_id": existing["_id"]}, {"$set": {"status": "cancelled", "cancelled_at": now()}})
    updated = await partner_subscriptions.find_one({"_id": existing["_id"]})
    await log_audit(current_user["id"], "partner_plan.cancelled", "organization", org_id, {"planCode": plan_code})

    revoked_bonus = await revoke_bundle_bonus_if_broken(
        partner_subscriptions, org_id,
        PARTNER_BONUS_TRIGGER_A, PARTNER_BONUS_TRIGGER_B, PARTNER_BONUS_CODE,
        get_active_partner_pillars,
    )
    cascaded = await cascade_cancel_dependent_addons(partner_subscriptions, partner_plans_collection, org_id, plan_code)

    return {"subscription": to_out(updated), "bonusRevoked": revoked_bonus, "addonsCancelled": cascaded}

import re

from fastapi import APIRouter, HTTPException, Depends

from app.db import organizations, users, organization_subscriptions, plans as plans_collection
from app.auth import get_current_user, require_internal, hash_password
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.phone import normalize_phone
from app.routers.referrals import REFERRAL_CREATOR_BUSINESS_TYPES

router = APIRouter(prefix="/api/orgs", tags=["orgs"], dependencies=[Depends(get_current_user)])


async def _pillars_and_monthly_totals_bulk(org_ids: list[str]) -> dict:
    """Manual-join replacement for orgs.js's two LATERAL subqueries: each
    active subscription's pillars (bundle plans expand to all their
    pillars) and a monthly-equivalent total (yearly plans divided by 12) --
    for every org_id given, in 2 queries total instead of a subscriptions
    query PLUS a plan lookup per subscription PER org (which used to scale
    directly with total business count, with no cap)."""
    if not org_ids:
        return {}
    subs = await organization_subscriptions.find({"org_id": {"$in": org_ids}, "status": "active"}).to_list(None)
    plan_codes = list({s["plan_code"] for s in subs if s.get("plan_code")})
    plan_docs = await plans_collection.find({"_id": {"$in": plan_codes}}).to_list(None) if plan_codes else []
    plans_by_code = {p["_id"]: p for p in plan_docs}

    subs_by_org: dict[str, list[dict]] = {}
    for s in subs:
        subs_by_org.setdefault(s["org_id"], []).append(s)

    result = {}
    for org_id in org_ids:
        active_pillars: set[str] = set()
        monthly_total = 0.0
        for sub in subs_by_org.get(org_id, []):
            plan = plans_by_code.get(sub["plan_code"])
            if not plan:
                continue
            if plan.get("is_bundle") and plan.get("bundle_pillars"):
                active_pillars.update(plan["bundle_pillars"])
            else:
                active_pillars.add(plan["_id"])
            if sub.get("billing_cycle") == "yearly":
                price = sub.get("price_at_purchase") or plan.get("yearly_price") or 0
                monthly_total += float(price) / 12
            else:
                price = sub.get("price_at_purchase") or plan.get("monthly_price") or 0
                monthly_total += float(price)
        result[org_id] = (list(active_pillars), monthly_total)
    return result


@router.get("", dependencies=[Depends(require_internal)])
@router.get("/", dependencies=[Depends(require_internal)])
async def list_orgs(status: str | None = None, q: str | None = None):
    filt: dict = {}
    if status:
        filt["status"] = status
    if q:
        filt["name"] = {"$regex": q, "$options": "i"}
    rows = await organizations.find(filt).sort("created_at", -1).limit(300).to_list(None)

    totals_by_org = await _pillars_and_monthly_totals_bulk([o["_id"] for o in rows])
    out = []
    for o in rows:
        pillars, monthly_total = totals_by_org.get(o["_id"], ([], 0.0))
        item = to_out(o)
        item["active_pillars"] = pillars
        item["monthly_total"] = monthly_total
        out.append(item)
    return {"organizations": out}


@router.get("/directory")
async def org_directory(q: str | None = None, current_user: dict = Depends(get_current_user)):
    """Lightweight, non-financial business lookup for a partner deciding who
    to send a partnership request to (see routers/partnerships.py's
    POST /requests) -- partner-shell only. Deliberately narrower than
    list_orgs above (which is internal-only and includes billing/pillar
    data): only businesses that can actually receive/create referrals
    (REFERRAL_CREATOR_BUSINESS_TYPES -- clinic/hospital/eye_hospital) are
    worth a partner requesting, and only name/city/business_type are
    returned, never subscription or financial fields.

    MUST be registered before GET /{org_id} below -- FastAPI matches routes
    in registration order, and a route registered after a path-parameter
    route would never be reached (the literal "directory" would instead be
    swallowed as if it were an {org_id})."""
    if current_user["appShell"] not in ("partner", "internal"):
        raise HTTPException(status_code=403, detail="Not authorized.")
    filt: dict = {"business_type": {"$in": list(REFERRAL_CREATOR_BUSINESS_TYPES)}}
    if q:
        filt["name"] = {"$regex": q, "$options": "i"}
    rows = await organizations.find(filt).sort("name", 1).limit(100).to_list(None)
    return {"organizations": [
        {"id": o["_id"], "name": o.get("name"), "city": o.get("city"), "businessType": o.get("business_type")}
        for o in rows
    ]}


@router.get("/{org_id}")
async def get_org(org_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] == "customer" and current_user["orgId"] != org_id:
        raise HTTPException(status_code=403, detail="Not authorized.")
    org = await organizations.find_one({"_id": org_id})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return {"organization": to_out(org)}


ALLOWED_ORG_PATCH_FIELDS = {
    "name": "name", "legalName": "legal_name", "city": "city", "state": "state",
    "address": "address", "pincode": "pincode", "phone": "phone", "email": "email",
    "website": "website", "logoUrl": "logo_url", "subscriptionPlan": "subscription_plan",
    "status": "status",
    # Where ROSKYRO sends this business's periodic Marketing Fee Payout
    # (see routers/settlements.py's marketing-payouts endpoints) -- distinct
    # from a partner's own payout_upi_id on the `partners` collection,
    # which is a different account for a different flow (a partner's own
    # profile, not the customer org record).
    "marketingPayoutUpiId": "marketing_payout_upi_id",
}


@router.patch("/{org_id}")
async def patch_org(org_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    is_owner_of_org = current_user["appShell"] == "customer" and current_user["orgId"] == org_id and current_user["role"] == "owner"
    if not is_owner_of_org and current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="Not authorized.")

    updates = {}
    for camel, snake in ALLOWED_ORG_PATCH_FIELDS.items():
        if camel in body:
            updates[snake] = body[camel]
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update.")
    updates["updated_at"] = now()

    result = await organizations.update_one({"_id": org_id}, {"$set": updates})
    updated = await organizations.find_one({"_id": org_id})
    if not updated:
        raise HTTPException(status_code=404, detail="Organization not found.")

    await log_audit(current_user["id"], "organization.updated", "organization", org_id, body)
    return {"organization": to_out(updated)}


@router.get("/{org_id}/team")
async def get_team(org_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] == "customer" and current_user["orgId"] != org_id:
        raise HTTPException(status_code=403, detail="Not authorized.")
    rows = await users.find({"org_id": org_id}).sort("created_at", 1).to_list(None)
    team = [{
        "id": u["_id"], "name": u.get("name"), "email": u.get("email"), "role": u.get("role"),
        "phone": u.get("phone"), "status": u.get("status"), "last_login_at": u.get("last_login_at"),
    } for u in rows]
    return {"team": team}


@router.post("/{org_id}/team", status_code=201)
async def invite_team_member(org_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    is_owner_of_org = current_user["appShell"] == "customer" and current_user["orgId"] == org_id and current_user["role"] == "owner"
    if not is_owner_of_org and current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="Not authorized.")

    name, email, role, phone, password = body.get("name"), body.get("email"), body.get("role"), body.get("phone"), body.get("password")
    if not name or not email or not role or not phone or not password:
        raise HTTPException(status_code=400, detail="name, email, mobile number, role and password are required.")

    existing = await users.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    normalized_phone = normalize_phone(phone)
    if len(normalized_phone) != 10:
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")
    existing_phone = await users.find_one({"phone": {"$regex": f"{re.escape(normalized_phone)}$"}})
    if existing_phone:
        raise HTTPException(status_code=409, detail="A user with this mobile number already exists.")

    user_id = new_id()
    doc = {
        "_id": user_id, "org_id": org_id, "name": name, "email": email,
        "password_hash": hash_password(password), "phone": phone, "role": role,
        "status": "active", "avatar_url": None, "last_login_at": None,
        "created_at": now(), "updated_at": now(),
    }
    await users.insert_one(doc)
    await log_audit(current_user["id"], "user.invited", "user", user_id, {"role": role})
    return {"user": {"id": user_id, "name": name, "email": email, "role": role, "phone": phone, "status": "active"}}

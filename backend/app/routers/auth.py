from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import users, organizations, tasks
from app.auth import hash_password, verify_password, create_access_token, get_current_user
from app.utils.roles import app_shell_for
from app.utils.audit import log_audit
from app.utils.ids import new_id, now
from app.utils.phone import normalize_phone

router = APIRouter(prefix="/api/auth", tags=["auth"])


def public_user(user: dict) -> dict:
    """Direct port of auth.js's publicUser()."""
    return {
        "id": user["id"],
        "orgId": user.get("org_id"),
        "name": user.get("name"),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "role": user.get("role"),
        "avatarUrl": user.get("avatar_url"),
        "orgName": user.get("org_name"),
        "businessType": user.get("business_type"),
        "isPartner": user.get("is_partner"),
        "subscriptionPlan": user.get("subscription_plan"),
        "appShell": app_shell_for(user.get("role")),
    }


class LoginBody(BaseModel):
    # Accepts EITHER an email address OR a mobile number -- whichever the
    # user types. Kept as one field (not separate email/phone fields) so
    # the login form can stay a single input.
    identifier: str
    password: str


class RegisterBody(BaseModel):
    orgName: str
    businessType: str | None = None
    city: str | None = None
    ownerName: str
    email: str
    # Required (not optional) -- every account's mobile number is also its
    # login identifier, per the "mobile number + password to log in"
    # requirement, so a self-registered owner must supply one at signup.
    phone: str
    password: str


@router.post("/login")
async def login(body: LoginBody):
    """Every account type (super admin, a doctor/clinic/hospital owner, a
    network partner admin) logs in with either their email or their
    mobile number, plus their password -- resolved by whichever the typed
    identifier looks like. A bare "@" check is enough to tell them apart
    since phone numbers never contain one."""
    identifier = body.identifier.strip()
    if "@" in identifier:
        user = await users.find_one({"email": {"$regex": f"^{identifier}$", "$options": "i"}})
    else:
        normalized = normalize_phone(identifier)
        user = await users.find_one({"phone": {"$regex": f"{normalized}$"}}) if normalized else None

    if not user:
        raise HTTPException(status_code=401, detail="Invalid mobile number/email or password.")

    ok = verify_password(body.password, user.get("password_hash") or "")
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid mobile number/email or password.")
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="Account is not active. Contact support.")

    await users.update_one({"_id": user["_id"]}, {"$set": {"last_login_at": now()}})
    await log_audit(user["_id"], "auth.login", "user", user["_id"])

    org = await organizations.find_one({"_id": user["org_id"]}) if user.get("org_id") else None
    merged = {
        "id": user["_id"],
        "org_id": user.get("org_id"),
        "name": user.get("name"),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "role": user.get("role"),
        "avatar_url": user.get("avatar_url"),
        "org_name": org.get("name") if org else None,
        "business_type": org.get("business_type") if org else None,
        "is_partner": org.get("is_partner") if org else None,
        "subscription_plan": org.get("subscription_plan") if org else None,
    }

    token = create_access_token(user["_id"], user["role"])
    return {"token": token, "user": public_user(merged)}


@router.post("/register", status_code=201)
async def register(body: RegisterBody):
    """Self-serve signup for a NEW healthcare business (owner + org together).
    Internal ROSKYRO staff and Partners are provisioned by an admin, not via
    public signup. NOTE: Mongo multi-document transactions require a replica
    set (not available with the in-sandbox mongomock client), so this is a
    sequential best-effort sequence rather than a single ACID transaction --
    on a real MongoDB deployment this could be wrapped in a client session
    transaction with zero other code changes."""
    existing = await users.find_one({"email": {"$regex": f"^{body.email}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    normalized_phone = normalize_phone(body.phone)
    if len(normalized_phone) != 10:
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")
    existing_phone = await users.find_one({"phone": {"$regex": f"{normalized_phone}$"}})
    if existing_phone:
        raise HTTPException(status_code=409, detail="An account with this mobile number already exists.")

    org_id = new_id()
    org_doc = {
        "_id": org_id,
        "name": body.orgName,
        "business_type": body.businessType or "clinic",
        "city": body.city,
        "phone": body.phone,
        "email": body.email,
        "status": "onboarding",
        "is_partner": False,
        "subscription_plan": None,
        "logo_url": None,
        "state": None,
        "address": None,
        "created_at": now(),
        "updated_at": now(),
    }
    await organizations.insert_one(org_doc)

    user_id = new_id()
    user_doc = {
        "_id": user_id,
        "org_id": org_id,
        "name": body.ownerName,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "phone": body.phone,
        "role": "owner",
        "status": "active",
        "avatar_url": None,
        "last_login_at": None,
        "created_at": now(),
        "updated_at": now(),
    }
    await users.insert_one(user_doc)

    await tasks.insert_one({
        "_id": new_id(),
        "org_id": org_id,
        "related_type": None,
        "related_id": None,
        "title": f"Onboard new business: {body.orgName}",
        "description": f"New signup via self-serve registration. Business type: {org_doc['business_type']}, city: {body.city or 'unknown'}.",
        "task_type": "onboarding",
        "assigned_role": "roskyro_ops_manager",
        "assigned_to": None,
        "priority": "high",
        "status": "open",
        "sla_hours": 24,
        "sla_due_at": now(),
        "created_by": None,
        "completed_at": None,
        "created_at": now(),
    })

    await log_audit(user_id, "auth.register", "organization", org_id)

    token = create_access_token(user_id, "owner")
    merged = {
        "id": user_id,
        "org_id": org_id,
        "name": body.ownerName,
        "email": body.email,
        "phone": body.phone,
        "role": "owner",
        "avatar_url": None,
        "org_name": org_doc["name"],
        "business_type": org_doc["business_type"],
        "is_partner": org_doc["is_partner"],
        "subscription_plan": org_doc["subscription_plan"],
    }
    return {"token": token, "user": public_user(merged)}


@router.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    merged = {
        "id": current_user["id"],
        "org_id": current_user.get("org_id"),
        "name": current_user.get("name"),
        "email": current_user.get("email"),
        "phone": current_user.get("phone"),
        "role": current_user.get("role"),
        "avatar_url": current_user.get("avatar_url"),
        "org_name": current_user.get("orgName"),
        "business_type": current_user.get("businessType"),
        "is_partner": current_user.get("isPartner"),
        "subscription_plan": current_user.get("subscriptionPlan"),
    }
    return {"user": public_user(merged)}

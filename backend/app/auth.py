import asyncio
from datetime import timedelta
from fastapi import Header, HTTPException, Depends
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRES_DAYS
from app.db import users, organizations
from app.utils.roles import app_shell_for, is_internal
from app.utils.pillars import get_active_pillars, get_active_partner_pillars
from app.utils.ids import now

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str, role: str) -> str:
    expire = now() + timedelta(days=JWT_EXPIRES_DAYS)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """Port of requireAuth middleware. Verifies the bearer JWT, loads the
    user (+ org, left-join style), computes appShell + activePillars, and
    returns a dict shaped like the original req.user object."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token.")
    token = authorization[len("Bearer "):]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    user = await users.find_one({"_id": payload.get("sub")})
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    if user.get("status") != "active":
        raise HTTPException(status_code=403, detail="Account is not active.")

    # PERFORMANCE: the org lookup and the pillar lookup both depend only on
    # user["org_id"] -- neither needs the other's result -- but they used to
    # run strictly one after the other, so every authenticated request in the
    # whole app paid both latencies in series before the endpoint body even
    # started. Running them concurrently makes the pair cost one round-trip
    # of wall-clock instead of two.
    app_shell = app_shell_for(user["role"])
    org_id = user.get("org_id")

    async def _load_org():
        if not org_id:
            return None
        return await organizations.find_one({"_id": org_id})

    async def _load_pillars():
        if app_shell == "customer":
            return await get_active_pillars(org_id)
        if app_shell == "partner":
            return await get_active_partner_pillars(org_id)
        return set()

    org, active_pillars = await asyncio.gather(_load_org(), _load_pillars())

    # Round 24: ROSKYRO's super admin can deactivate a business/partner
    # account (see routers/orgs.py's POST /{org_id}/deactivate) -- every
    # user at that org gets locked out immediately, the same way a
    # deactivated team member already gets locked out via the `status`
    # check above. Deliberately a separate `is_suspended` flag rather than
    # the org's existing `status` field: every org is created with
    # status "onboarding" and nothing else in this codebase ever flips it
    # to "active" (see register() in this same flow), so gating on
    # `status != "active"` would lock out every existing business/partner
    # that has ever signed up.
    if org and org.get("is_suspended"):
        raise HTTPException(status_code=403, detail="This organization's account has been deactivated. Contact ROSKYRO support.")

    return {
        "id": user["_id"],
        "org_id": user.get("org_id"),
        "orgId": user.get("org_id"),
        "name": user.get("name"),
        "email": user.get("email"),
        "phone": user.get("phone"),
        "role": user.get("role"),
        "status": user.get("status"),
        "avatar_url": user.get("avatar_url"),
        "avatarUrl": user.get("avatar_url"),
        "orgName": org.get("name") if org else None,
        "businessType": org.get("business_type") if org else None,
        "businessCategory": org.get("business_category") if org else None,
        "isPartner": org.get("is_partner") if org else None,
        "subscriptionPlan": org.get("subscription_plan") if org else None,
        "appShell": app_shell,
        "activePillars": active_pillars,
    }


def require_roles(*roles: str):
    """Dependency factory — port of requireRoles(...roles) middleware."""

    async def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action.")
        return current_user

    return dependency


async def require_internal(current_user: dict = Depends(get_current_user)) -> dict:
    if not is_internal(current_user["role"]):
        raise HTTPException(status_code=403, detail="Internal ROSKYRO team access only.")
    return current_user

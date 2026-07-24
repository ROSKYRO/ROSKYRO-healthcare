from datetime import timedelta
from fastapi import Header, HTTPException, Depends
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.config import JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRES_DAYS
from app.db import users, organizations
from app.utils.roles import app_shell_for, is_internal
from app.utils.pillars import get_active_pillars
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

    org = None
    if user.get("org_id"):
        org = await organizations.find_one({"_id": user["org_id"]})

    app_shell = app_shell_for(user["role"])
    active_pillars = await get_active_pillars(user.get("org_id")) if app_shell == "customer" else set()

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

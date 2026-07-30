"""Manage ROSKYRO's own internal team (the roskyro_* roles that appear on
the Team Roster / Team Dashboard) -- as distinct from routers/orgs.py's
`/{org_id}/team`, which manages a BUSINESS's own staff/doctors, not
ROSKYRO's.

Before this file existed, there was NO create/edit/deactivate path for
ROSKYRO's internal team anywhere in the product. Team Roster
(routers/tasks.py's team_roster()) is a read-only workload view -- it
lists whoever already has a roskyro_* role in `users`, but those rows only
ever got there via the one-time demo seed (app/seed.py). Renaming a
seeded person, changing someone's role, or adding a new internal hire had
no UI and no API -- only a direct database edit could do it, which isn't
something a live production site's admin should ever need to reach for
just to onboard a new ops hire.

Restricted to `roskyro_admin` only, same precedent already set for
Pricing & Payments (routers/settings.py) and Password Requests
(routers/password_resets.py) -- this can create another admin account
and can deactivate any internal user, so it isn't opened to every
internal role the way Team Roster's read-only view is.

Deactivation, not deletion: a team member who leaves is set to
status="inactive" (same field auth.py's login() already checks), never
hard-deleted. Hard-deleting a user would strand every task, audit log
entry, and referral action they ever created (assigned_to/created_by
fields elsewhere all reference this same _id) -- deactivating blocks
their login immediately without breaking any of that history, and it's
reversible if someone comes back or a deactivation was a mistake.
"""
import re

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.db import users
from app.auth import hash_password, require_roles
from app.utils.roles import ROSKYRO_ROLES
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out
from app.utils.phone import normalize_phone

router = APIRouter(prefix="/api/team-members", tags=["team-members"])


def _member_out(u: dict) -> dict:
    out = to_out(u)
    out.pop("password_hash", None)
    return out


@router.get("")
@router.get("/")
async def list_team_members(current_user: dict = Depends(require_roles("roskyro_admin"))):
    # $in against the explicit role registry, not a "roskyro_" prefix
    # regex -- ROSKYRO_ROLES (app/utils/roles.py) is the single source of
    # truth for which roles are internal; matching against it directly
    # means this list can never drift out of sync with what app_shell_for()
    # and every permission check elsewhere actually treats as internal.
    rows = await users.find({"role": {"$in": ROSKYRO_ROLES}}).sort([("role", 1), ("name", 1)]).to_list(None)
    return {"members": [_member_out(u) for u in rows]}


class CreateMemberBody(BaseModel):
    name: str
    email: str
    phone: str
    role: str
    password: str = Field(min_length=6)


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_team_member(body: CreateMemberBody, current_user: dict = Depends(require_roles("roskyro_admin"))):
    name = body.name.strip()
    email = body.email.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    if body.role not in ROSKYRO_ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(ROSKYRO_ROLES)}.")

    existing = await users.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}})
    if existing:
        raise HTTPException(status_code=409, detail="A user with this email already exists.")

    normalized_phone = normalize_phone(body.phone)
    if len(normalized_phone) != 10:
        raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")
    existing_phone = await users.find_one({"phone": {"$regex": f"{re.escape(normalized_phone)}$"}})
    if existing_phone:
        raise HTTPException(status_code=409, detail="A user with this mobile number already exists.")

    user_id = new_id()
    doc = {
        # org_id is always None here -- these are ROSKYRO's own internal
        # staff, never tied to a business, matching how every seeded
        # internal user already looks (see app/seed.py) and what
        # app_shell_for() expects for the "internal" shell.
        "_id": user_id, "org_id": None, "name": name, "email": email,
        "password_hash": hash_password(body.password), "phone": body.phone, "role": body.role,
        "status": "active", "avatar_url": None, "last_login_at": None,
        "created_at": now(), "updated_at": now(),
    }
    await users.insert_one(doc)
    await log_audit(current_user["id"], "team_member.created", "user", user_id, {"role": body.role})
    return {"member": _member_out(doc)}


class UpdateMemberBody(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    role: str | None = None
    status: str | None = None
    newPassword: str | None = None


@router.patch("/{member_id}")
async def update_team_member(member_id: str, body: UpdateMemberBody, current_user: dict = Depends(require_roles("roskyro_admin"))):
    existing = await users.find_one({"_id": member_id})
    # Scoped to ROSKYRO_ROLES, same as the list endpoint above -- without
    # this check an admin could accidentally reach into a completely
    # unrelated business owner's or partner's account through this
    # endpoint just by guessing/knowing their user id.
    if not existing or existing.get("role") not in ROSKYRO_ROLES:
        raise HTTPException(status_code=404, detail="Team member not found.")

    updates = {}
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty.")
        updates["name"] = name
    if body.email is not None:
        email = body.email.strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email cannot be empty.")
        dupe = await users.find_one({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}, "_id": {"$ne": member_id}})
        if dupe:
            raise HTTPException(status_code=409, detail="A user with this email already exists.")
        updates["email"] = email
    if body.phone is not None:
        normalized_phone = normalize_phone(body.phone)
        if len(normalized_phone) != 10:
            raise HTTPException(status_code=400, detail="Please enter a valid 10-digit mobile number.")
        dupe = await users.find_one({"phone": {"$regex": f"{re.escape(normalized_phone)}$"}, "_id": {"$ne": member_id}})
        if dupe:
            raise HTTPException(status_code=409, detail="A user with this mobile number already exists.")
        updates["phone"] = body.phone
    if body.role is not None:
        if body.role not in ROSKYRO_ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of: {', '.join(ROSKYRO_ROLES)}.")
        updates["role"] = body.role
    if body.status is not None:
        if body.status not in ("active", "inactive"):
            raise HTTPException(status_code=400, detail="status must be 'active' or 'inactive'.")
        updates["status"] = body.status
    if body.newPassword is not None:
        if len(body.newPassword) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
        updates["password_hash"] = hash_password(body.newPassword)

    # Guard: never let the LAST active admin be demoted or deactivated --
    # that would lock every admin-only screen (this one included, plus
    # Pricing & Payments and Password Requests) with no remaining account
    # able to reverse it. A fresh database boot always seeds exactly one
    # roskyro_admin, so this only ever bites the specific case of removing
    # the very last one.
    losing_admin_status = (
        existing.get("role") == "roskyro_admin" and existing.get("status") == "active"
        and (
            ("role" in updates and updates["role"] != "roskyro_admin")
            or ("status" in updates and updates["status"] != "active")
        )
    )
    if losing_admin_status:
        other_active_admins = await users.count_documents(
            {"role": "roskyro_admin", "status": "active", "_id": {"$ne": member_id}}
        )
        if other_active_admins == 0:
            raise HTTPException(status_code=400, detail="Cannot remove the last active admin account.")

    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    updates["updated_at"] = now()

    await users.update_one({"_id": member_id}, {"$set": updates})
    updated = await users.find_one({"_id": member_id})
    await log_audit(
        current_user["id"], "team_member.updated", "user", member_id,
        {k: v for k, v in body.model_dump(exclude_unset=True).items() if k != "newPassword"},
    )
    return {"member": _member_out(updated)}

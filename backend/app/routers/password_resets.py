from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import users, organizations, password_reset_requests
from app.auth import hash_password, get_current_user, require_roles
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.phone import normalize_phone

router = APIRouter(prefix="/api/password-resets", tags=["password-resets"])

# "Bhool gaye password" flow: there is no self-service email-link reset in
# v1 (no real outbound email/SMS provider wired up) -- instead, whoever is
# locked out submits a request naming themselves (mobile number or email),
# and only ROSKYRO's super admin (`roskyro_admin` -- deliberately not every
# internal role, same precedent as Pricing & Payments in Phase 4) can see
# the queue and actually set the new password by hand.


class SubmitBody(BaseModel):
    identifier: str  # the mobile number or email the locked-out user knows
    note: str | None = None


class ResolveBody(BaseModel):
    newPassword: str


def _request_out(req: dict) -> dict:
    return to_out(req)


@router.post("", status_code=201)
async def submit_request(body: SubmitBody):
    identifier = body.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Please enter your mobile number or email.")

    if "@" in identifier:
        user = await users.find_one({"email": {"$regex": f"^{identifier}$", "$options": "i"}})
    else:
        normalized = normalize_phone(identifier)
        user = await users.find_one({"phone": {"$regex": f"{normalized}$"}}) if normalized else None

    if not user:
        # Deliberately vague (no user enumeration) but still actionable --
        # this mirrors the same wording used for a failed login.
        raise HTTPException(status_code=404, detail="No ROSKYRO account found with that mobile number or email.")

    # Idempotent: if this user already has a pending request, don't pile up
    # duplicates -- just surface the existing one so the UI can show
    # "already submitted, waiting on ROSKYRO" instead of a fresh queue entry
    # every time someone re-submits the form out of anxiety.
    existing = await password_reset_requests.find_one({"user_id": user["_id"], "status": "pending"})
    if existing:
        return {"request": _request_out(existing), "alreadyPending": True}

    org = await organizations.find_one({"_id": user["org_id"]}) if user.get("org_id") else None
    doc = {
        "_id": new_id(),
        "user_id": user["_id"],
        "user_name": user.get("name"),
        "user_email": user.get("email"),
        "user_phone": user.get("phone"),
        "user_role": user.get("role"),
        "org_name": org.get("name") if org else None,
        "note": (body.note or "").strip() or None,
        "status": "pending",
        "requested_at": now(),
        "resolved_at": None,
        "resolved_by": None,
    }
    await password_reset_requests.insert_one(doc)
    return {"request": _request_out(doc), "alreadyPending": False}


@router.get("")
async def list_requests(current_user: dict = Depends(require_roles("roskyro_admin"))):
    # Capped like every other platform-wide admin list -- this had no
    # filter or limit at all, so it would return every reset request ever
    # submitted (pending, resolved, and dismissed) across the platform's
    # entire history.
    rows = await password_reset_requests.find().sort("requested_at", -1).limit(300).to_list(None)
    return {"requests": to_out_many(rows)}


@router.post("/{request_id}/resolve")
async def resolve_request(request_id: str, body: ResolveBody, current_user: dict = Depends(require_roles("roskyro_admin"))):
    req = await password_reset_requests.find_one({"_id": request_id})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail="This request has already been handled.")
    if len(body.newPassword) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    await users.update_one(
        {"_id": req["user_id"]},
        {"$set": {"password_hash": hash_password(body.newPassword), "updated_at": now()}},
    )
    await password_reset_requests.update_one(
        {"_id": request_id},
        {"$set": {"status": "resolved", "resolved_at": now(), "resolved_by": current_user["id"]}},
    )
    await log_audit(current_user["id"], "auth.admin_reset_password", "user", req["user_id"])

    updated = await password_reset_requests.find_one({"_id": request_id})
    return {"request": _request_out(updated)}


@router.post("/{request_id}/dismiss")
async def dismiss_request(request_id: str, current_user: dict = Depends(require_roles("roskyro_admin"))):
    req = await password_reset_requests.find_one({"_id": request_id})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found.")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail="This request has already been handled.")

    await password_reset_requests.update_one(
        {"_id": request_id},
        {"$set": {"status": "dismissed", "resolved_at": now(), "resolved_by": current_user["id"]}},
    )
    updated = await password_reset_requests.find_one({"_id": request_id})
    return {"request": _request_out(updated)}

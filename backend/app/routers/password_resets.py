import re

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

from app.db import users, organizations, password_reset_requests
from app.auth import hash_password, get_current_user, require_roles
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.phone import normalize_phone
from app.utils.rate_limit import enforce_rate_limit

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
async def submit_request(body: SubmitBody, request: Request = None):
    """Fixed: this used to raise a 404 "No ROSKYRO account found..." when
    the identifier didn't match any user, and a 201 with the created (or
    already-pending) request when it did -- two distinguishable responses
    to an unauthenticated, unthrottled endpoint that takes an arbitrary
    email/phone. That's a textbook user-enumeration oracle: anyone could
    script through a list of emails/phone numbers and learn exactly which
    ones have a ROSKYRO account, on a healthcare platform where that alone
    is sensitive (it confirms someone is a patient-facing business's staff
    member, or worse, could be paired with other guesses to profile who
    uses the platform). The comment on this endpoint even claimed it was
    "deliberately vague (no user enumeration)" -- it wasn't; the response
    *shape* gave it away regardless of wording.

    Now: the HTTP response is identical (201, `{alreadyPending: bool}`)
    whether or not the identifier matches a real account -- a request row
    is only ever written to the DB when a real user is found, so a
    non-existent identifier silently does nothing but still "succeeds"
    from the caller's point of view. The frontend (Login.jsx) already only
    reads `alreadyPending`, never anything account-specific from the
    response, so this needed no frontend change.

    Also added: rate limiting (previously this endpoint had none at all,
    unlike auth.py's login() and public_booking.py's book_slot(), the
    other two unauthenticated DB-writing endpoints in this codebase --
    the same enumeration attack above is only actually practical at scale
    without a limit on requests per IP)."""
    client_ip = request.client.host if (request and request.client) else "unknown"
    enforce_rate_limit("password_reset_submit", client_ip)

    identifier = body.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="Please enter your mobile number or email.")

    if "@" in identifier:
        # re.escape() -- see auth.py's login() for why: this is another
        # unauthenticated, user-controlled regex lookup.
        user = await users.find_one({"email": {"$regex": f"^{re.escape(identifier)}$", "$options": "i"}})
    else:
        normalized = normalize_phone(identifier)
        user = await users.find_one({"phone": {"$regex": f"{re.escape(normalized)}$"}}) if normalized else None

    if not user:
        # Same response shape as every other outcome below -- see the
        # docstring above for why this must not be distinguishable.
        return {"alreadyPending": False}

    # Idempotent: if this user already has a pending request, don't pile up
    # duplicates -- just surface the existing one so the UI can show
    # "already submitted, waiting on ROSKYRO" instead of a fresh queue entry
    # every time someone re-submits the form out of anxiety.
    existing = await password_reset_requests.find_one({"user_id": user["_id"], "status": "pending"})
    if existing:
        return {"alreadyPending": True}

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
    return {"alreadyPending": False}


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

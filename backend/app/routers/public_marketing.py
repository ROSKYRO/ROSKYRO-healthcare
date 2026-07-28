from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db import contact_leads, newsletter_subscribers
from app.utils.ids import new_id, now, to_out
from app.utils.rate_limit import enforce_rate_limit

router = APIRouter(prefix="/api/public", tags=["public-marketing"])

# Both endpoints here back the public marketing site (Contact Us page form,
# footer newsletter box) -- intentionally no-auth, same reasoning as
# public_booking.py: a visitor filling these out has no ROSKYRO account yet.
# There's no admin UI to review these leads yet (out of scope for this
# pass) -- they land in Mongo so nothing submitted by a real visitor is
# ever lost, and a review screen can be added later without any schema
# change needed here.
#
# Both bodies use typed Pydantic models with max_length caps -- they used
# to be raw `body: dict` with `(body.get("field") or "").strip()`, which
# raised an unhandled AttributeError/TypeError (-> raw 500) whenever a
# field was sent as a non-string JSON value (e.g. {"email": 12345}), and
# had no cap on freeform text size. FastAPI now rejects those with a clean
# 422 before the handler even runs.


class ContactLeadBody(BaseModel):
    # `name` is business-required (checked below) but deliberately NOT a
    # required Pydantic field: a required field makes FastAPI reject a
    # missing/blank name with a generic 422 before this handler ever runs,
    # which would silently change the API's error contract (the existing
    # test suite -- and presumably the frontend -- expects the handler's
    # own clean "Your name is required." 400 below, not a Pydantic 422).
    name: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=200)
    businessName: str | None = Field(None, max_length=200)
    businessType: str | None = Field(None, max_length=100)
    city: str | None = Field(None, max_length=100)
    message: str | None = Field(None, max_length=5000)
    reason: str | None = Field(None, max_length=50)


@router.post("/contact", status_code=201)
async def submit_contact_lead(body: ContactLeadBody, request: Request = None):
    enforce_rate_limit("public_contact", _client_ip(request))
    name = (body.name or "").strip()
    phone = (body.phone or "").strip()
    email = (body.email or "").strip()
    business_name = (body.businessName or "").strip()
    business_type = (body.businessType or "").strip()
    city = (body.city or "").strip()
    message = (body.message or "").strip()
    reason = (body.reason or "general").strip()

    if not name:
        raise HTTPException(status_code=400, detail="Your name is required.")
    if not phone and not email:
        raise HTTPException(status_code=400, detail="Please share a phone number or email so we can reach you.")

    doc = {
        "_id": new_id(), "name": name, "phone": phone or None, "email": email or None,
        "business_name": business_name or None, "business_type": business_type or None,
        "city": city or None, "message": message or None, "reason": reason,
        "status": "new", "created_at": now(),
    }
    await contact_leads.insert_one(doc)
    return {"lead": to_out(doc)}


class NewsletterSubscribeBody(BaseModel):
    # Same reasoning as ContactLeadBody.name above: kept optional at the
    # Pydantic layer so a missing email still falls through to the
    # handler's own "Please enter a valid email address." 400 rather than
    # a generic Pydantic 422.
    email: str | None = Field(None, max_length=200)


@router.post("/newsletter-subscribe", status_code=201)
async def subscribe_newsletter(body: NewsletterSubscribeBody, request: Request = None):
    enforce_rate_limit("public_newsletter", _client_ip(request))
    email = (body.email or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    existing = await newsletter_subscribers.find_one({"email": email})
    if existing:
        return {"subscriber": to_out(existing), "alreadySubscribed": True}

    doc = {"_id": new_id(), "email": email, "created_at": now()}
    await newsletter_subscribers.insert_one(doc)
    return {"subscriber": to_out(doc), "alreadySubscribed": False}


def _client_ip(request) -> str:
    if request is None:
        return "unknown"
    return request.client.host if request.client else "unknown"

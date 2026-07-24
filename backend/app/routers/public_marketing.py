from fastapi import APIRouter, HTTPException

from app.db import contact_leads, newsletter_subscribers
from app.utils.ids import new_id, now, to_out

router = APIRouter(prefix="/api/public", tags=["public-marketing"])

# Both endpoints here back the public marketing site (Contact Us page form,
# footer newsletter box) -- intentionally no-auth, same reasoning as
# public_booking.py: a visitor filling these out has no ROSKYRO account yet.
# There's no admin UI to review these leads yet (out of scope for this
# pass) -- they land in Mongo so nothing submitted by a real visitor is
# ever lost, and a review screen can be added later without any schema
# change needed here.


@router.post("/contact", status_code=201)
async def submit_contact_lead(body: dict):
    name = (body.get("name") or "").strip()
    phone = (body.get("phone") or "").strip()
    email = (body.get("email") or "").strip()
    business_name = (body.get("businessName") or "").strip()
    business_type = (body.get("businessType") or "").strip()
    city = (body.get("city") or "").strip()
    message = (body.get("message") or "").strip()
    reason = (body.get("reason") or "general").strip()

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


@router.post("/newsletter-subscribe", status_code=201)
async def subscribe_newsletter(body: dict):
    email = (body.get("email") or "").strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    existing = await newsletter_subscribers.find_one({"email": email})
    if existing:
        return {"subscriber": to_out(existing), "alreadySubscribed": True}

    doc = {"_id": new_id(), "email": email, "created_at": now()}
    await newsletter_subscribers.insert_one(doc)
    return {"subscriber": to_out(doc), "alreadySubscribed": False}

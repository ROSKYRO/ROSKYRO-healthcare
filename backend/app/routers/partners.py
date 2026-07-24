from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import partners, organizations, partner_categories, partner_services, users, partner_agreements, settlement_rules
from app.auth import get_current_user, require_internal
from app.utils.plans import require_plan
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/partners",
    tags=["partners"],
    # NOTE: only get_current_user is a router-wide dependency. require_plan("connect")
    # is applied per-route below -- only to the endpoints that browse/search the paid
    # partner directory (list_partners, recommendations, get_partner). Categories,
    # self-registration ("Become a Partner"), viewing/editing your own partner profile,
    # and internal verification must stay free of the Networking Marketing plan gate, since listing
    # yourself as a partner is free by design.
    dependencies=[Depends(get_current_user)],
)


async def _referral_bonus_amounts_for(partner_ids: list[str]) -> dict:
    """Each partner can self-declare the default Referral Bonus -- a flat
    rupee amount, not a percentage -- they pay a referring business per
    completed referral (see `settlements.py`'s `/my-rate` endpoint) --
    this is just the 'partner' scope settlement rule, the same one the
    referral-completion settlement engine already resolves against (see
    routers/referrals.py). Surfaced here so the partner directory can show
    it to businesses deciding who to partner with, without duplicating the
    amount anywhere."""
    if not partner_ids:
        return {}
    rows = await settlement_rules.find({
        "scope": "partner", "partner_id": {"$in": partner_ids},
        "is_active": True, "settlement_type": "flat_fee",
    }).to_list(None)
    return {r["partner_id"]: r.get("flat_fee_amount") for r in rows}


async def _enrich_partner(p: dict, referral_bonus_amount: float | None = None) -> dict:
    org = await organizations.find_one({"_id": p["org_id"]})
    cat = await partner_categories.find_one({"_id": p.get("category_id")})
    out = to_out(p)
    out["org_name"] = org.get("name") if org else None
    out["city"] = org.get("city") if org else None
    out["state"] = org.get("state") if org else None
    out["logo_url"] = org.get("logo_url") if org else None
    out["category_name"] = cat.get("name") if cat else None
    out["category_slug"] = cat.get("slug") if cat else None
    out["referral_bonus_amount"] = referral_bonus_amount
    return out


@router.get("/categories")
async def list_categories():
    rows = await partner_categories.find({"is_active": True}).sort([("sort_order", 1), ("name", 1)]).to_list(None)
    return {"categories": to_out_many(rows)}


@router.get("", dependencies=[Depends(require_plan("connect"))])
@router.get("/", dependencies=[Depends(require_plan("connect"))])
async def list_partners(
    category: str | None = None,
    city: str | None = None,
    q: str | None = None,
    verifiedOnly: str | None = None,
    availableOnly: str | None = None,
):
    filt: dict = {}
    if category:
        cat = await partner_categories.find_one({"slug": category})
        filt["category_id"] = cat["_id"] if cat else "__none__"
    if verifiedOnly == "true":
        filt["verification_status"] = "verified"
    if availableOnly == "true":
        filt["is_available_now"] = True

    rows = await partners.find(filt).to_list(None)
    rate_map = await _referral_bonus_amounts_for([p["_id"] for p in rows])
    enriched = [await _enrich_partner(p, rate_map.get(p["_id"])) for p in rows]

    if city:
        needle = city.lower()
        enriched = [
            e for e in enriched
            if (e.get("city") and needle in e["city"].lower())
            or (needle in [c.lower() for c in (e.get("coverage_cities") or [])])
        ]
    if q:
        needle = q.lower()
        enriched = [
            e for e in enriched
            if (e.get("org_name") and needle in e["org_name"].lower())
            or (e.get("contact_person") and needle in e["contact_person"].lower())
        ]

    enriched.sort(key=lambda e: (not e.get("preferred_partner"), -(e.get("rating_avg") or 0)))
    return {"partners": enriched[:200]}


@router.get("/recommendations", dependencies=[Depends(require_plan("connect"))])
async def recommendations(category: str, city: str | None = None):
    """'AI' best-partner recommendation. Since there is no paid AI API in
    v1, this is a deterministic scoring heuristic that stands in for the
    AI-generated ranking described in the RPN/HREN specs -- the same
    response shape a future LLM-backed ranker would return, so swapping the
    implementation later requires no frontend changes."""
    cat = await partner_categories.find_one({"slug": category})
    if not cat:
        return {"generatedBy": "ai_heuristic_v1", "note": "", "recommendations": []}

    rows = await partners.find({"category_id": cat["_id"]}).to_list(None)
    rate_map = await _referral_bonus_amounts_for([p["_id"] for p in rows])
    scored = []
    for p in rows:
        org = await organizations.find_one({"_id": p["org_id"]})
        if city:
            needle = city.lower()
            org_city = (org.get("city") or "").lower() if org else ""
            coverage = [c.lower() for c in (p.get("coverage_cities") or [])]
            if needle not in org_city and needle not in coverage:
                continue
        score = (float(p.get("rating_avg") or 0) * 20)
        score += 15 if p.get("verification_status") == "verified" else 0
        score += 10 if p.get("preferred_partner") else 0
        score += 10 if p.get("is_available_now") else 0
        completed = p.get("total_referrals_completed") or 0
        received = p.get("total_referrals_received") or 0
        if completed > 0:
            score += min(20, (completed / max(received, 1)) * 20)
        art = p.get("avg_report_time_hours")
        if art is not None and art < 24:
            score += 10
        out = to_out(p)
        out["org_name"] = org.get("name") if org else None
        out["city"] = org.get("city") if org else None
        out["category_name"] = cat.get("name")
        out["referral_bonus_amount"] = rate_map.get(p["_id"])
        out["ai_score"] = score
        scored.append(out)

    scored.sort(key=lambda e: -e["ai_score"])
    return {
        "generatedBy": "ai_heuristic_v1",
        "note": "AI-drafted recommendation. A ROSKYRO team member (or the referring doctor) makes the final selection — this list is a suggestion, not an auto-assignment, per the AI + Human operating model.",
        "recommendations": scored[:5],
    }


@router.get("/me")
async def my_partner(current_user: dict = Depends(get_current_user)):
    # Looked up by org_id, not appShell -- a business can self-register as a
    # free Networking Marketing partner from its regular customer-shell account (see
    # POST /register below), so a customer-shell user checking "did my
    # application go through / is it verified yet" needs this to work too,
    # not just partner-shell accounts managing an existing listing.
    if not current_user.get("orgId"):
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")
    p = await partners.find_one({"org_id": current_user["orgId"]})
    if not p:
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")
    rate_map = await _referral_bonus_amounts_for([p["_id"]])
    return {"partner": await _enrich_partner(p, rate_map.get(p["_id"]))}


@router.get("/{partner_id}", dependencies=[Depends(require_plan("connect"))])
async def get_partner(partner_id: str):
    p = await partners.find_one({"_id": partner_id})
    if not p:
        raise HTTPException(status_code=404, detail="Partner not found.")
    org = await organizations.find_one({"_id": p["org_id"]})
    out = to_out(p)
    out["org_name"] = org.get("name") if org else None
    out["city"] = org.get("city") if org else None
    out["state"] = org.get("state") if org else None
    out["address"] = org.get("address") if org else None
    out["phone"] = org.get("phone") if org else None
    out["email"] = org.get("email") if org else None
    out["logo_url"] = org.get("logo_url") if org else None
    rate_map = await _referral_bonus_amounts_for([partner_id])
    out["referral_bonus_amount"] = rate_map.get(partner_id)
    cat = await partner_categories.find_one({"_id": p.get("category_id")})
    out["category_name"] = cat.get("name") if cat else None
    out["category_slug"] = cat.get("slug") if cat else None

    services = await partner_services.find({"partner_id": partner_id, "is_active": True}).sort("name", 1).to_list(None)
    agreements = await partner_agreements.find({"partner_id": partner_id}).sort("created_at", -1).to_list(None)

    return {"partner": out, "services": to_out_many(services), "agreements": to_out_many(agreements)}


class ServiceItem(BaseModel):
    name: str
    description: str | None = None
    price: float | None = None
    priceUnit: str | None = None
    turnaroundTime: str | None = None


class RegisterPartnerBody(BaseModel):
    categorySlug: str
    coverageArea: str | None = None
    coverageCities: list[str] | None = None
    turnaroundTime: str | None = None
    contactPerson: str | None = None
    contactPhone: str | None = None
    contactEmail: str | None = None
    services: list[ServiceItem] | None = None


@router.post("/register", status_code=201)
async def register_partner(body: RegisterPartnerBody, current_user: dict = Depends(get_current_user)):
    if not current_user.get("orgId"):
        raise HTTPException(status_code=400, detail="Only organization users can register as a partner.")

    cat = await partner_categories.find_one({"slug": body.categorySlug})
    if not cat:
        raise HTTPException(status_code=400, detail="Unknown category.")

    await organizations.update_one({"_id": current_user["orgId"]}, {"$set": {"is_partner": True}})

    partner_id = new_id()
    partner_doc = {
        "_id": partner_id,
        "org_id": current_user["orgId"],
        "category_id": cat["_id"],
        "coverage_area": body.coverageArea,
        "coverage_cities": body.coverageCities,
        "turnaround_time": body.turnaroundTime,
        "contact_person": body.contactPerson or current_user["name"],
        "contact_phone": body.contactPhone,
        "contact_email": body.contactEmail or current_user["email"],
        "verification_status": "pending",
        "verified_by": None,
        "verified_at": None,
        "working_hours": None,
        "is_available_now": False,
        "preferred_partner": False,
        "payout_upi_id": None,
        "payout_note": None,
        "rating_avg": None,
        "total_referrals_received": 0,
        "total_referrals_completed": 0,
        "avg_report_time_hours": None,
        "created_at": now(),
        "updated_at": now(),
    }
    await partners.insert_one(partner_doc)

    if body.services:
        for s in body.services:
            await partner_services.insert_one({
                "_id": new_id(), "partner_id": partner_id, "name": s.name,
                "description": s.description, "price": s.price,
                "price_unit": s.priceUnit or "per service", "turnaround_time": s.turnaroundTime,
                "is_active": True, "created_at": now(),
            })

    from app.db import tasks as tasks_col
    await tasks_col.insert_one({
        "_id": new_id(), "org_id": current_user["orgId"], "related_type": "partner_verification",
        "related_id": partner_id, "title": "Verify new partner application",
        "description": f"Category: {body.categorySlug}. Submitted by {current_user['name']} ({current_user['email']}).",
        "task_type": "partner_verification", "assigned_role": "roskyro_ops_manager", "assigned_to": None,
        "priority": "high", "status": "open", "sla_hours": 48, "sla_due_at": now(),
        "created_by": None, "completed_at": None, "created_at": now(),
    })

    await log_audit(current_user["id"], "partner.registered", "partner", partner_id)
    return {"partner": to_out(partner_doc)}


class VerifyBody(BaseModel):
    decision: str
    note: str | None = None


@router.post("/{partner_id}/verify", dependencies=[Depends(require_internal)])
async def verify_partner(partner_id: str, body: VerifyBody, current_user: dict = Depends(get_current_user)):
    if body.decision not in ("verified", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'verified' or 'rejected'.")

    p = await partners.find_one({"_id": partner_id})
    if not p:
        raise HTTPException(status_code=404, detail="Partner not found.")

    await partners.update_one({"_id": partner_id}, {"$set": {
        "verification_status": body.decision, "verified_by": current_user["id"],
        "verified_at": now(), "updated_at": now(),
    }})
    updated = await partners.find_one({"_id": partner_id})

    from app.db import tasks as tasks_col
    await tasks_col.update_many(
        {"related_type": "partner_verification", "related_id": partner_id, "status": {"$ne": "done"}},
        {"$set": {"status": "done", "completed_at": now()}},
    )

    owner = await users.find_one({"org_id": updated["org_id"], "role": "owner"})
    if owner:
        await notify(
            owner["_id"], "partner_verification_decision",
            "Your partner profile is verified" if body.decision == "verified" else "Your partner application needs changes",
            body.note or ("You are now a verified partner in the ROSKYRO network." if body.decision == "verified" else "Please review and resubmit your partner details."),
            "partner", partner_id,
        )

    await log_audit(current_user["id"], f"partner.{body.decision}", "partner", partner_id, {"note": body.note})
    return {"partner": to_out(updated)}


ALLOWED_PATCH_FIELDS = {
    "coverageArea": "coverage_area", "coverageCities": "coverage_cities",
    "turnaroundTime": "turnaround_time", "workingHours": "working_hours",
    "isAvailableNow": "is_available_now", "contactPerson": "contact_person",
    "contactPhone": "contact_phone", "contactEmail": "contact_email",
    "preferredPartner": "preferred_partner", "payoutUpiId": "payout_upi_id",
    "payoutNote": "payout_note",
}


@router.patch("/{partner_id}")
async def patch_partner(partner_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    own = await partners.find_one({"_id": partner_id})
    if not own:
        raise HTTPException(status_code=404, detail="Partner not found.")
    if own["org_id"] != current_user["orgId"] and current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="You can only edit your own partner profile.")

    updates = {}
    for camel, snake in ALLOWED_PATCH_FIELDS.items():
        if camel in body:
            updates[snake] = body[camel]
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update.")
    updates["updated_at"] = now()

    await partners.update_one({"_id": partner_id}, {"$set": updates})
    updated = await partners.find_one({"_id": partner_id})
    return {"partner": to_out(updated)}

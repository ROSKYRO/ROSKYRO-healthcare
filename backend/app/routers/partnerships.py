"""A business's own designated "my partner" per service category -- a
lighter-weight relationship layered ON TOP of the open partner
marketplace (see routers/partners.py's list/search-by-service), not a
replacement for it. Confirmed with the user explicitly: referral creation
stays fully open -- a business can refer to ANY partner in a category at
any time, whether or not a partnership is set. Setting a partnership just
gives that partner a "★ Your Partner" shortcut at the top of the
quick-referral search results (see routers/partners.py's
search_by_service, which now also marks/sorts on this).

Two ways a partnership comes to exist:
1. The business directly sets/swaps its partner for a category (browsing
   the same open marketplace as always) -- POST /partnerships.
2. A partner pitches itself to a business it wants to work with --
   POST /partnerships/requests -- and the business Accepts/Declines it.

At most ONE partnership per (org_id, category_id) is ever "active" --
picking a new partner (directly, or by accepting a request) always ends
whichever one was active there before, never leaves two active at once.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import partnerships, partnership_requests, partners, partner_categories, organizations, users
from app.auth import get_current_user, require_internal
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.notify import notify
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/partnerships", tags=["partnerships"], dependencies=[Depends(get_current_user)])


def _is_business_owner(current_user: dict) -> bool:
    return current_user["appShell"] == "customer" and current_user["role"] == "owner"


async def _set_partnership(org_id: str, partner: dict, initiated_by: str, actor_user_id: str | None) -> dict:
    """Shared "make this partner active for its category on this business"
    step -- used by both the direct set/swap endpoint and by accepting an
    incoming partnership request, so the two paths can never disagree on
    what "becoming the active partner" actually does: end whatever was
    active for this (org_id, category_id) before, then insert the new
    active row. Never two active rows for the same (org_id, category_id)
    at once."""
    category_id = partner["category_id"]
    await partnerships.update_many(
        {"org_id": org_id, "category_id": category_id, "status": "active"},
        {"$set": {"status": "ended", "ended_at": now(), "ended_by": actor_user_id, "ended_reason": "replaced"}},
    )
    doc = {
        "_id": new_id(), "org_id": org_id, "category_id": category_id, "partner_id": partner["_id"],
        "status": "active", "initiated_by": initiated_by,
        "created_at": now(), "ended_at": None, "ended_by": None, "ended_reason": None,
    }
    await partnerships.insert_one(doc)
    return doc


async def _enrich_partnerships(rows: list[dict]) -> list[dict]:
    """Batch-fetch category + partner + partner's org ONCE each via $in --
    same fixed-query-count pattern used everywhere else in this codebase's
    list endpoints, instead of a find_one per row."""
    if not rows:
        return []
    category_ids = list({r["category_id"] for r in rows if r.get("category_id")})
    partner_ids = list({r["partner_id"] for r in rows if r.get("partner_id")})

    category_docs = await partner_categories.find({"_id": {"$in": category_ids}}).to_list(None) if category_ids else []
    categories_by_id = {c["_id"]: c for c in category_docs}
    partner_docs = await partners.find({"_id": {"$in": partner_ids}}).to_list(None) if partner_ids else []
    partners_by_id = {p["_id"]: p for p in partner_docs}

    org_ids = list({p["org_id"] for p in partner_docs if p.get("org_id")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}

    out = []
    for r in rows:
        cat = categories_by_id.get(r.get("category_id"))
        p = partners_by_id.get(r.get("partner_id"))
        p_org = orgs_by_id.get(p["org_id"]) if p else None
        item = to_out(r)
        item["category_name"] = cat.get("name") if cat else None
        item["category_slug"] = cat.get("slug") if cat else None
        item["partner_org_name"] = p_org.get("name") if p_org else None
        item["partner_city"] = p_org.get("city") if p_org else None
        item["partner_verification_status"] = p.get("verification_status") if p else None
        out.append(item)
    return out


@router.get("")
@router.get("/")
async def list_partnerships(orgId: str | None = None, current_user: dict = Depends(get_current_user)):
    """Every category this business currently has an active designated
    partner for. Any user in the business (not just the owner) can view
    this -- same as viewing the team roster -- only setting/ending one is
    owner-restricted below."""
    if current_user["appShell"] == "customer":
        org_id = current_user["orgId"]
    elif orgId:
        org_id = orgId
    else:
        raise HTTPException(status_code=400, detail="orgId is required.")

    rows = await partnerships.find({"org_id": org_id, "status": "active"}).to_list(None)
    return {"partnerships": await _enrich_partnerships(rows)}


class SetPartnershipBody(BaseModel):
    partnerId: str


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def set_partnership(body: SetPartnershipBody, current_user: dict = Depends(get_current_user)):
    """The business directly picks (or swaps) its partner for a category,
    choosing from the same open marketplace as the quick-referral flow --
    no restriction on which partner can be chosen. Whichever partner was
    previously active for that category (if any) is automatically ended,
    never left running alongside the new one."""
    if not _is_business_owner(current_user) and current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="Only the business owner (or ROSKYRO internal) can set a partnership.")

    partner = await partners.find_one({"_id": body.partnerId})
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found.")

    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else partner["org_id"]
    doc = await _set_partnership(org_id, partner, initiated_by="business", actor_user_id=current_user["id"])
    await log_audit(current_user["id"], "partnership.set", "partnership", doc["_id"], {"partnerId": partner["_id"]})
    enriched = await _enrich_partnerships([doc])
    return {"partnership": enriched[0]}


@router.post("/{category_id}/end")
async def end_partnership(category_id: str, current_user: dict = Depends(get_current_user)):
    """Ends this business's active partnership for a category -- no
    designated partner until a new one is set (via POST above, or by
    accepting a future request). Referral creation is never affected --
    the full marketplace stays available regardless."""
    if not _is_business_owner(current_user) and current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="Only the business owner (or ROSKYRO internal) can end a partnership.")

    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else None
    if not org_id:
        raise HTTPException(status_code=400, detail="Only a business account can end its own partnership this way.")

    existing = await partnerships.find_one({"org_id": org_id, "category_id": category_id, "status": "active"})
    if not existing:
        raise HTTPException(status_code=404, detail="No active partnership for this category.")

    await partnerships.update_one(
        {"_id": existing["_id"]},
        {"$set": {"status": "ended", "ended_at": now(), "ended_by": current_user["id"], "ended_reason": "ended_by_business"}},
    )
    await log_audit(current_user["id"], "partnership.ended", "partnership", existing["_id"], {"categoryId": category_id})
    return {"ended": True}


class SendRequestBody(BaseModel):
    orgId: str
    message: str | None = None


@router.post("/requests", status_code=201)
async def send_partnership_request(body: SendRequestBody, current_user: dict = Depends(get_current_user)):
    """A partner's own pitch to a specific business: "let me be your
    partner for my category." Idempotent while pending -- re-sending to
    the same business just returns the existing pending request instead
    of piling up duplicates (same pattern as password_resets.py's
    submit_request)."""
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Only a partner account can send a partnership request.")

    partner = await partners.find_one({"org_id": current_user["orgId"]})
    if not partner:
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")

    target_org = await organizations.find_one({"_id": body.orgId})
    if not target_org:
        raise HTTPException(status_code=404, detail="Business not found.")
    owner = await users.find_one({"org_id": body.orgId, "role": "owner"})
    if not owner:
        # No accessible business account to decide this request later --
        # reject up front rather than creating an orphaned request nobody
        # can ever act on.
        raise HTTPException(status_code=400, detail="This organization doesn't have a business account to request a partnership with.")

    existing = await partnership_requests.find_one({
        "org_id": body.orgId, "partner_id": partner["_id"], "status": "pending",
    })
    if existing:
        return {"request": to_out(existing), "alreadyPending": True}

    doc = {
        "_id": new_id(), "org_id": body.orgId, "partner_id": partner["_id"], "category_id": partner["category_id"],
        "message": (body.message or "").strip() or None, "status": "pending",
        "requested_at": now(), "decided_at": None, "decided_by": None,
    }
    await partnership_requests.insert_one(doc)

    await notify(
        owner["_id"], "partnership_request", "New partnership request",
        "A partner would like to become your designated partner.", "partnership_request", doc["_id"],
    )
    await log_audit(current_user["id"], "partnership_request.sent", "partnership_request", doc["_id"], {"orgId": body.orgId})
    return {"request": to_out(doc), "alreadyPending": False}


@router.get("/requests")
async def list_partnership_requests(current_user: dict = Depends(get_current_user)):
    """Incoming requests for a business (owner/internal), or outbound
    requests a partner has sent, depending which shell is asking."""
    if current_user["appShell"] == "customer":
        if not _is_business_owner(current_user):
            raise HTTPException(status_code=403, detail="Only the business owner can view partnership requests.")
        rows = await partnership_requests.find({"org_id": current_user["orgId"]}).sort("requested_at", -1).to_list(None)
    elif current_user["appShell"] == "internal":
        rows = await partnership_requests.find({}).sort("requested_at", -1).limit(300).to_list(None)
    elif current_user["appShell"] == "partner":
        partner = await partners.find_one({"org_id": current_user["orgId"]})
        if not partner:
            return {"requests": []}
        rows = await partnership_requests.find({"partner_id": partner["_id"]}).sort("requested_at", -1).to_list(None)
    else:
        raise HTTPException(status_code=403, detail="Not authorized.")

    # Batch-fetch whatever's needed to label each row for its viewer.
    category_ids = list({r["category_id"] for r in rows if r.get("category_id")})
    category_docs = await partner_categories.find({"_id": {"$in": category_ids}}).to_list(None) if category_ids else []
    categories_by_id = {c["_id"]: c for c in category_docs}

    if current_user["appShell"] == "customer":
        partner_ids = list({r["partner_id"] for r in rows if r.get("partner_id")})
        partner_docs = await partners.find({"_id": {"$in": partner_ids}}).to_list(None) if partner_ids else []
        partners_by_id = {p["_id"]: p for p in partner_docs}
        org_ids = list({p["org_id"] for p in partner_docs if p.get("org_id")})
        org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
        orgs_by_id = {o["_id"]: o for o in org_docs}
        out = []
        for r in rows:
            p = partners_by_id.get(r.get("partner_id"))
            p_org = orgs_by_id.get(p["org_id"]) if p else None
            item = to_out(r)
            item["category_name"] = categories_by_id.get(r.get("category_id"), {}).get("name")
            item["partner_org_name"] = p_org.get("name") if p_org else None
            out.append(item)
        return {"requests": out}

    org_ids = list({r["org_id"] for r in rows if r.get("org_id")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}
    out = []
    for r in rows:
        org = orgs_by_id.get(r.get("org_id"))
        item = to_out(r)
        item["category_name"] = categories_by_id.get(r.get("category_id"), {}).get("name")
        item["org_name"] = org.get("name") if org else None
        out.append(item)
    return {"requests": out}


class DecideRequestBody(BaseModel):
    decision: str


@router.post("/requests/{request_id}/decide")
async def decide_partnership_request(request_id: str, body: DecideRequestBody, current_user: dict = Depends(get_current_user)):
    """The business Accepts or Declines an incoming request. Accepting
    runs through the exact same _set_partnership step the direct
    set-partner endpoint uses -- so it correctly ends whatever partner was
    previously active for that category, same as any other swap."""
    if body.decision not in ("accepted", "declined"):
        raise HTTPException(status_code=400, detail="decision must be 'accepted' or 'declined'.")

    req = await partnership_requests.find_one({"_id": request_id})
    if not req:
        raise HTTPException(status_code=404, detail="Partnership request not found.")
    if not (_is_business_owner(current_user) and current_user["orgId"] == req["org_id"]) and current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="Only the business owner (or ROSKYRO internal) can decide this request.")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail="This request has already been decided.")

    await partnership_requests.update_one(
        {"_id": request_id},
        {"$set": {"status": body.decision, "decided_at": now(), "decided_by": current_user["id"]}},
    )

    if body.decision == "accepted":
        partner = await partners.find_one({"_id": req["partner_id"]})
        if not partner:
            raise HTTPException(status_code=404, detail="The requesting partner no longer exists.")
        await _set_partnership(req["org_id"], partner, initiated_by="partner_request", actor_user_id=current_user["id"])

    await log_audit(current_user["id"], f"partnership_request.{body.decision}", "partnership_request", request_id, {})
    updated = await partnership_requests.find_one({"_id": request_id})
    return {"request": to_out(updated)}

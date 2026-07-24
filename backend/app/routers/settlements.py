from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.db import settlement_rules, settlements, referrals, organizations, partners, statements
from app.auth import get_current_user, require_internal
from app.utils.roles import is_internal
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(prefix="/api/settlements", tags=["settlements"], dependencies=[Depends(get_current_user)])


@router.get("/rules")
async def list_rules(current_user: dict = Depends(get_current_user)):
    filt: dict = {}
    if current_user["appShell"] == "customer":
        filt["org_id"] = current_user["orgId"]
    elif current_user["appShell"] == "partner":
        p = await partners.find_one({"org_id": current_user["orgId"]})
        filt["partner_id"] = p["_id"] if p else "__none__"
    rows = await settlement_rules.find(filt).sort("created_at", -1).to_list(None)
    return {"rules": to_out_many(rows)}


class RuleBody(BaseModel):
    scope: str
    orgId: str | None = None
    partnerId: str | None = None
    categoryId: str | None = None
    settlementType: str
    flatFeeAmount: float | None = None
    percentageRate: float | None = None
    customTerms: str | None = None


@router.get("/my-rate")
async def get_my_rate(current_user: dict = Depends(get_current_user)):
    """A partner's own self-declared default commission (%) -- the 'partner'
    scope settlement rule they set via PUT /my-rate below. Returns null if
    they haven't set one yet (falls through to org/platform defaults per
    the usual resolution order when a referral actually completes)."""
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner accounts only.")
    p = await partners.find_one({"org_id": current_user["orgId"]})
    if not p:
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")
    rule = await settlement_rules.find_one({"scope": "partner", "partner_id": p["_id"], "is_active": True})
    return {"rate": to_out(rule)}


class CommissionRateBody(BaseModel):
    percentageRate: float


@router.put("/my-rate")
async def set_my_rate(body: CommissionRateBody, current_user: dict = Depends(get_current_user)):
    """Partners self-declare the default commission (%) they'll pay a
    referring business per completed referral -- shown publicly in the
    partner directory (see routers/partners.py's `_commission_rates_for`)
    so businesses can compare partners and decide who to work with, per
    "har partner apna commission show karta hai, use base par businesses
    use apna partner banayenge." This creates/updates the 'partner' scope
    settlement rule -- priority #2 in the org_partner_pair > partner > org
    > platform resolution order that routers/referrals.py already uses
    when a referral completes, so no separate resolution logic is needed.
    ROSKYRO internal team can still negotiate a business-specific
    org_partner_pair override on top of this via POST /rules, same as
    before -- that still wins over a partner's own self-set default."""
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner accounts only.")
    if body.percentageRate < 0 or body.percentageRate > 100:
        raise HTTPException(status_code=400, detail="Commission rate must be between 0 and 100.")

    p = await partners.find_one({"org_id": current_user["orgId"]})
    if not p:
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")

    existing = await settlement_rules.find_one({"scope": "partner", "partner_id": p["_id"], "is_active": True})
    if existing:
        await settlement_rules.update_one(
            {"_id": existing["_id"]},
            {"$set": {"settlement_type": "percentage", "percentage_rate": body.percentageRate, "updated_at": now()}},
        )
        rule_id = existing["_id"]
    else:
        rule_id = new_id()
        await settlement_rules.insert_one({
            "_id": rule_id, "scope": "partner", "org_id": None, "partner_id": p["_id"], "category_id": None,
            "settlement_type": "percentage", "flat_fee_amount": None, "percentage_rate": body.percentageRate,
            "custom_terms": None, "is_active": True, "created_by": current_user["id"], "created_at": now(),
        })

    updated = await settlement_rules.find_one({"_id": rule_id})
    await log_audit(current_user["id"], "settlement_rule.self_set", "settlement_rule", rule_id, {"percentageRate": body.percentageRate})
    return {"rate": to_out(updated)}


@router.post("/rules", status_code=201, dependencies=[Depends(require_internal)])
async def create_rule(body: RuleBody, current_user: dict = Depends(get_current_user)):
    if body.scope not in ("platform", "org", "partner", "org_partner_pair"):
        raise HTTPException(status_code=400, detail="Invalid scope.")
    if body.settlementType not in ("none", "flat_fee", "percentage", "custom"):
        raise HTTPException(status_code=400, detail="Invalid settlementType.")

    doc = {
        "_id": new_id(), "scope": body.scope, "org_id": body.orgId, "partner_id": body.partnerId,
        "category_id": body.categoryId, "settlement_type": body.settlementType,
        "flat_fee_amount": body.flatFeeAmount, "percentage_rate": body.percentageRate,
        "custom_terms": body.customTerms, "is_active": True,
        "created_by": current_user["id"], "created_at": now(),
    }
    await settlement_rules.insert_one(doc)
    await log_audit(current_user["id"], "settlement_rule.created", "settlement_rule", doc["_id"], body.model_dump())
    return {"rule": to_out(doc)}


@router.get("")
@router.get("/")
async def list_settlements(status: str | None = None, period: str | None = None, current_user: dict = Depends(get_current_user)):
    filt: dict = {}
    if current_user["appShell"] == "customer":
        filt["org_id"] = current_user["orgId"]
    elif current_user["appShell"] == "partner":
        org_partners = await partners.find({"org_id": current_user["orgId"]}).to_list(None)
        filt["partner_id"] = {"$in": [p["_id"] for p in org_partners]}
    if status:
        filt["status"] = status
    if period:
        filt["period_month"] = period

    rows = await settlements.find(filt).sort("created_at", -1).limit(300).to_list(None)
    out = []
    for s in rows:
        r = await referrals.find_one({"_id": s["referral_id"]})
        ro = await organizations.find_one({"_id": s["org_id"]})
        p = await partners.find_one({"_id": s["partner_id"]})
        po = await organizations.find_one({"_id": p["org_id"]}) if p else None
        item = to_out(s)
        item["referral_code"] = r.get("referral_code") if r else None
        item["org_name"] = ro.get("name") if ro else None
        item["partner_org_name"] = po.get("name") if po else None
        item["partner_payout_upi_id"] = p.get("payout_upi_id") if p else None
        out.append(item)
    return {"settlements": out}


@router.post("/{settlement_id}/mark-paid")
async def mark_paid(settlement_id: str, current_user: dict = Depends(get_current_user)):
    """ROSKYRO never moves this money. The referring business pays the
    partner directly at the partner's payout UPI ID, outside the app, so
    the referring org (the payer) is who self-reports it here.

    This is a two-sided confirmation, not a one-click "paid" -- the payer
    clicking this only records their own claim (`payer_marked_paid_at`).
    The settlement's `status` stays "pending" until the partner (the one
    actually receiving the money) independently confirms receipt via
    POST /{id}/confirm-received below. This prevents a business from
    getting referral credit just by claiming payment without the partner
    ever actually receiving it.

    ROSKYRO internal team is the one exception: an internal "mark paid"
    is a dispute-resolution override (a business reported the payment
    through support instead of using the app) and finalizes the
    settlement immediately, bypassing the partner-confirmation step --
    ROSKYRO staff are vouching for the payment having happened, not
    self-reporting it."""
    settlement = await settlements.find_one({"_id": settlement_id})
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found.")

    is_payer_org = current_user["appShell"] == "customer" and current_user["orgId"] == settlement["org_id"]
    if not is_payer_org and not is_internal(current_user["role"]):
        raise HTTPException(status_code=403, detail="Only the referring business (who owes this commission) or the ROSKYRO team can mark it paid.")

    if is_internal(current_user["role"]) and not is_payer_org:
        # Dispute-resolution override: finalize immediately, no partner
        # confirmation needed.
        await settlements.update_one({"_id": settlement_id}, {"$set": {
            "status": "paid", "paid_at": now(),
            "payer_marked_paid_at": settlement.get("payer_marked_paid_at") or now(),
            "confirmed_by": "internal_override",
        }})
    else:
        if settlement.get("payer_marked_paid_at"):
            raise HTTPException(status_code=400, detail="Already marked paid — waiting for the partner to confirm receipt.")
        await settlements.update_one({"_id": settlement_id}, {"$set": {"payer_marked_paid_at": now()}})

    updated = await settlements.find_one({"_id": settlement_id})
    await log_audit(current_user["id"], "settlement.marked_paid", "settlement", settlement_id, {"markedBy": current_user["appShell"]})
    return {"settlement": to_out(updated)}


@router.post("/{settlement_id}/confirm-received")
async def confirm_received(settlement_id: str, current_user: dict = Depends(get_current_user)):
    """The other half of the two-sided confirmation: only the partner
    actually receiving the commission (the payee) can confirm they got
    it, and only after the payer has claimed they paid. Only this
    confirmation finalizes the settlement to status "paid" -- until then
    it stays "pending" no matter what the payer clicked, per the rule
    that a payer's own claim is never enough on its own."""
    settlement = await settlements.find_one({"_id": settlement_id})
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found.")

    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Only the receiving partner can confirm receipt of commission.")
    p = await partners.find_one({"org_id": current_user["orgId"]})
    if not p or p["_id"] != settlement["partner_id"]:
        raise HTTPException(status_code=403, detail="You can only confirm receipt of commission owed to your own partner profile.")
    if settlement["status"] == "paid":
        raise HTTPException(status_code=400, detail="This settlement is already confirmed as paid.")
    if not settlement.get("payer_marked_paid_at"):
        raise HTTPException(status_code=400, detail="The referring business hasn't marked this as paid yet — nothing to confirm.")

    await settlements.update_one({"_id": settlement_id}, {"$set": {
        "status": "paid", "paid_at": now(), "confirmed_by": current_user["id"],
    }})
    updated = await settlements.find_one({"_id": settlement_id})
    await log_audit(current_user["id"], "settlement.confirmed_received", "settlement", settlement_id, {})
    return {"settlement": to_out(updated)}


@router.get("/statements")
async def list_statements(partyType: str | None = None, partyId: str | None = None, period: str | None = None):
    filt: dict = {}
    if partyType:
        filt["party_type"] = partyType
    if partyId:
        filt["party_id"] = partyId
    if period:
        filt["period_month"] = period
    rows = await statements.find(filt).sort("period_month", -1).to_list(None)
    return {"statements": to_out_many(rows)}

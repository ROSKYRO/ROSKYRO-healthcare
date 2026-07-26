from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel

from app.db import settlement_rules, settlements, referrals, organizations, partners, partner_categories, statements, platform_settings, marketing_payouts, subscription_renewals
from app.auth import get_current_user, require_internal, require_roles
from app.utils.roles import is_internal
from app.utils.audit import log_audit
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.invoices import render_marketing_payout_invoice_pdf

router = APIRouter(prefix="/api/settlements", tags=["settlements"], dependencies=[Depends(get_current_user)])


@router.get("/rules")
async def list_rules(current_user: dict = Depends(get_current_user)):
    # A referring business never sees Marketing Fee amounts -- their
    # dashboard only shows which partner accepted/completed their referral
    # (see routers/referrals.py) plus their own incoming Marketing Fee
    # Payout (see /marketing-payouts and /marketing-fee-rate below). The
    # per-partner/per-org fee RATE that determines what a partner owes
    # ROSKYRO per referral is internal/partner-facing only.
    if current_user["appShell"] == "customer":
        raise HTTPException(status_code=403, detail="Marketing Fee rates aren't shown on the business dashboard.")
    filt: dict = {}
    if current_user["appShell"] == "partner":
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
    customTerms: str | None = None


@router.get("/my-rate")
async def get_my_rate(current_user: dict = Depends(get_current_user)):
    """A partner's own self-declared default Marketing Fee (flat rupees) --
    the amount the partner pays ROSKYRO per completed referral sent to
    them, treated as a marketing/lead-gen fee rather than a commission paid
    to the referring business. This is the 'partner' scope settlement rule
    they set via PUT /my-rate below. Returns null if they haven't set one
    yet (falls through to org/platform defaults per the usual resolution
    order when a referral actually completes)."""
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner accounts only.")
    p = await partners.find_one({"org_id": current_user["orgId"]})
    if not p:
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")
    rule = await settlement_rules.find_one({"scope": "partner", "partner_id": p["_id"], "is_active": True})
    return {"rate": to_out(rule)}


class ReferralBonusRateBody(BaseModel):
    flatFeeAmount: float


@router.put("/my-rate")
async def set_my_rate(body: ReferralBonusRateBody, current_user: dict = Depends(get_current_user)):
    """Partners self-declare the default Marketing Fee (a flat rupee amount
    -- percentage-of-service-price commission has been removed entirely)
    they'll pay ROSKYRO per completed referral sent to them by a business
    -- shown publicly in the partner directory so businesses can compare
    partners and decide who to work with. Patient referrals are treated as
    marketing the referring business does for the partner, so this fee is
    paid to ROSKYRO (see mark-paid/confirm-received below), not directly to
    the referring business -- ROSKYRO separately pays referring businesses
    a periodic Marketing Fee Payout (a fixed % of fees collected) instead.
    This creates/updates the 'partner' scope settlement rule -- priority #2
    in the org_partner_pair > partner > org > platform resolution order
    that routers/referrals.py already uses when a referral completes, so no
    separate resolution logic is needed. ROSKYRO internal team can still
    negotiate a business-specific org_partner_pair override on top of this
    via POST /rules, same as before -- that still wins over a partner's own
    self-set default."""
    if current_user["appShell"] != "partner":
        raise HTTPException(status_code=403, detail="Partner accounts only.")
    if body.flatFeeAmount < 0:
        raise HTTPException(status_code=400, detail="Marketing Fee amount cannot be negative.")

    p = await partners.find_one({"org_id": current_user["orgId"]})
    if not p:
        raise HTTPException(status_code=404, detail="Partner profile not found for this account.")

    existing = await settlement_rules.find_one({"scope": "partner", "partner_id": p["_id"], "is_active": True})
    if existing:
        await settlement_rules.update_one(
            {"_id": existing["_id"]},
            {"$set": {"settlement_type": "flat_fee", "flat_fee_amount": body.flatFeeAmount, "percentage_rate": None, "updated_at": now()}},
        )
        rule_id = existing["_id"]
    else:
        rule_id = new_id()
        await settlement_rules.insert_one({
            "_id": rule_id, "scope": "partner", "org_id": None, "partner_id": p["_id"], "category_id": None,
            "settlement_type": "flat_fee", "flat_fee_amount": body.flatFeeAmount, "percentage_rate": None,
            "custom_terms": None, "is_active": True, "created_by": current_user["id"], "created_at": now(),
        })

    updated = await settlement_rules.find_one({"_id": rule_id})
    await log_audit(current_user["id"], "settlement_rule.self_set", "settlement_rule", rule_id, {"flatFeeAmount": body.flatFeeAmount})
    return {"rate": to_out(updated)}


class PlatformRateBody(BaseModel):
    flatFeeAmount: float | None = None


@router.get("/platform-rate", dependencies=[Depends(require_internal)])
async def get_platform_rate():
    """The platform-wide fallback Marketing Fee -- only used when a
    completed referral matches none of the more specific rules (a
    negotiated org_partner_pair override, the partner's own self-set rate,
    a business-specific org override, or the partner's category default).
    See the resolution order in routers/referrals.py."""
    rule = await settlement_rules.find_one({"scope": "platform", "is_active": True})
    return {"rate": to_out(rule)}


@router.put("/platform-rate", dependencies=[Depends(require_roles("roskyro_admin"))])
async def set_platform_rate(body: PlatformRateBody, current_user: dict = Depends(get_current_user)):
    if body.flatFeeAmount is not None and body.flatFeeAmount < 0:
        raise HTTPException(status_code=400, detail="Marketing Fee amount cannot be negative.")
    settlement_type = "flat_fee" if body.flatFeeAmount is not None else "none"
    existing = await settlement_rules.find_one({"scope": "platform", "is_active": True})
    if existing:
        await settlement_rules.update_one(
            {"_id": existing["_id"]},
            {"$set": {"settlement_type": settlement_type, "flat_fee_amount": body.flatFeeAmount, "percentage_rate": None, "updated_at": now()}},
        )
        rule_id = existing["_id"]
    else:
        rule_id = new_id()
        await settlement_rules.insert_one({
            "_id": rule_id, "scope": "platform", "org_id": None, "partner_id": None, "category_id": None,
            "settlement_type": settlement_type, "flat_fee_amount": body.flatFeeAmount, "percentage_rate": None,
            "custom_terms": None, "is_active": True, "created_by": current_user["id"], "created_at": now(),
        })
    updated = await settlement_rules.find_one({"_id": rule_id})
    await log_audit(current_user["id"], "settlement_rule.platform_rate_updated", "settlement_rule", rule_id, {"flatFeeAmount": body.flatFeeAmount})
    return {"rate": to_out(updated)}


@router.get("/category-rates", dependencies=[Depends(require_internal)])
async def list_category_rates():
    """Every Networking Marketing partner category alongside its own
    category-level default Marketing Fee (if ROSKYRO has set one). Exists
    because a partner's own self-set flat fee (or the platform default, if
    they haven't set one) previously applied the exact same rupee amount
    whether the completed referral was for a ~₹200 blood test or an
    ~₹8,000 MRI scan -- this lets ROSKYRO set sensible category-appropriate
    defaults (e.g. a lower default for Blood Test Labs, a higher one for
    MRI Centers) that only kick in when nothing more specific (a
    negotiated business-partner pair, the partner's own rate, or a
    business-specific override) applies. See the resolution order in
    routers/referrals.py."""
    cats = await partner_categories.find({"is_active": True}).sort([("sort_order", 1), ("name", 1)]).to_list(None)
    rules = await settlement_rules.find({"scope": "category", "is_active": True}).to_list(None)
    rule_by_cat = {r["category_id"]: r for r in rules}
    out = []
    for c in cats:
        rule = rule_by_cat.get(c["_id"])
        out.append({
            "category_id": c["_id"], "category_name": c["name"], "category_slug": c["slug"],
            "group_name": c["group_name"], "group_slug": c["group_slug"],
            "flat_fee_amount": rule.get("flat_fee_amount") if rule else None,
            "settlement_type": rule.get("settlement_type") if rule else "none",
        })
    return {"categoryRates": out}


class CategoryRateBody(BaseModel):
    flatFeeAmount: float | None = None


@router.put("/category-rates/{category_id}", dependencies=[Depends(require_roles("roskyro_admin"))])
async def set_category_rate(category_id: str, body: CategoryRateBody, current_user: dict = Depends(get_current_user)):
    cat = await partner_categories.find_one({"_id": category_id})
    if not cat:
        raise HTTPException(status_code=404, detail="Unknown category.")
    if body.flatFeeAmount is not None and body.flatFeeAmount < 0:
        raise HTTPException(status_code=400, detail="Marketing Fee amount cannot be negative.")
    settlement_type = "flat_fee" if body.flatFeeAmount is not None else "none"
    existing = await settlement_rules.find_one({"scope": "category", "category_id": category_id, "is_active": True})
    if existing:
        await settlement_rules.update_one(
            {"_id": existing["_id"]},
            {"$set": {"settlement_type": settlement_type, "flat_fee_amount": body.flatFeeAmount, "percentage_rate": None, "updated_at": now()}},
        )
        rule_id = existing["_id"]
    else:
        rule_id = new_id()
        await settlement_rules.insert_one({
            "_id": rule_id, "scope": "category", "org_id": None, "partner_id": None, "category_id": category_id,
            "settlement_type": settlement_type, "flat_fee_amount": body.flatFeeAmount, "percentage_rate": None,
            "custom_terms": None, "is_active": True, "created_by": current_user["id"], "created_at": now(),
        })
    updated = await settlement_rules.find_one({"_id": rule_id})
    await log_audit(current_user["id"], "settlement_rule.category_rate_updated", "settlement_rule", rule_id, {"categoryId": category_id, "flatFeeAmount": body.flatFeeAmount})
    return {"rate": to_out(updated)}


@router.post("/rules", status_code=201, dependencies=[Depends(require_roles("roskyro_admin"))])
async def create_rule(body: RuleBody, current_user: dict = Depends(get_current_user)):
    if body.scope not in ("platform", "org", "partner", "org_partner_pair", "category"):
        raise HTTPException(status_code=400, detail="Invalid scope.")
    if body.scope == "category" and not body.categoryId:
        raise HTTPException(status_code=400, detail="categoryId is required for the category scope.")
    # Percentage-based settlement has been removed entirely -- Referral
    # Bonus is always a flat rupee amount (or "none"/"custom").
    if body.settlementType not in ("none", "flat_fee", "custom"):
        raise HTTPException(status_code=400, detail="Invalid settlementType.")

    if body.scope == "category":
        # Guard against ending up with two simultaneously-active "category"
        # rules for the same category_id -- set_category_rate (the PUT
        # /category-rates/{id} endpoint the admin UI actually uses) already
        # upserts safely, but this generic endpoint used to insert
        # unconditionally, so a rule created here could silently coexist
        # with one later edited via the UI. The referral-completion
        # resolution loop's find_one({"scope": "category", ...}) would then
        # return whichever of the two Mongo happens to pick, independently
        # of what the admin UI last showed as saved.
        await settlement_rules.update_many(
            {"scope": "category", "category_id": body.categoryId, "is_active": True},
            {"$set": {"is_active": False, "updated_at": now()}},
        )

    doc = {
        "_id": new_id(), "scope": body.scope, "org_id": body.orgId, "partner_id": body.partnerId,
        "category_id": body.categoryId, "settlement_type": body.settlementType,
        "flat_fee_amount": body.flatFeeAmount, "percentage_rate": None,
        "custom_terms": body.customTerms, "is_active": True,
        "created_by": current_user["id"], "created_at": now(),
    }
    await settlement_rules.insert_one(doc)
    await log_audit(current_user["id"], "settlement_rule.created", "settlement_rule", doc["_id"], body.model_dump())
    return {"rule": to_out(doc)}


@router.get("")
@router.get("/")
async def list_settlements(status: str | None = None, period: str | None = None, current_user: dict = Depends(get_current_user)):
    # Per-referral Marketing Fee amounts (what a partner owes/paid ROSKYRO)
    # are never shown to the referring business -- their dashboard is
    # limited to referral status/tracking (routers/referrals.py) plus their
    # own incoming Marketing Fee Payout (marketing-payouts/marketing-fee-rate
    # below), which is a separate, already-aggregated figure.
    if current_user["appShell"] == "customer":
        raise HTTPException(status_code=403, detail="Marketing Fee settlement details aren't shown on the business dashboard.")
    filt: dict = {}
    if current_user["appShell"] == "partner":
        org_partners = await partners.find({"org_id": current_user["orgId"]}).to_list(None)
        filt["partner_id"] = {"$in": [p["_id"] for p in org_partners]}
    if status:
        filt["status"] = status
    if period:
        filt["period_month"] = period

    platform = await platform_settings.find_one({"_id": 1})
    roskyro_upi_id = platform.get("upi_id") if platform else None

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
        # Marketing Fee is paid by the partner TO ROSKYRO, not to the
        # referring business, so the relevant payout account here is
        # ROSKYRO's own collection UPI ID (see /api/settings/payment).
        item["roskyro_payout_upi_id"] = roskyro_upi_id
        out.append(item)
    return {"settlements": out}


class MarkPaidBody(BaseModel):
    # Optional UTR/transaction reference the partner attaches as proof of
    # payment. ROSKYRO deliberately doesn't accept file/screenshot uploads
    # anywhere in this app (no document storage) -- a text reference number
    # is the equivalent proof here, and it's shown to ROSKYRO internal on
    # the settlements oversight page before they confirm-received below.
    paymentReference: str | None = None


@router.post("/{settlement_id}/mark-paid")
async def mark_paid(settlement_id: str, body: MarkPaidBody = MarkPaidBody(), current_user: dict = Depends(get_current_user)):
    """Patient Referral -> Marketing model: a completed referral is treated
    as the referring business doing marketing for the partner (bringing
    them a patient), so the per-referral Marketing Fee is owed by the
    PARTNER, and it's paid straight to ROSKYRO -- not to the referring
    business. So the partner (the payer) is who self-reports it here.

    This is a two-sided confirmation, not a one-click "paid" -- the payer
    clicking this only records their own claim (`payer_marked_paid_at`,
    optionally with a `payment_reference`). The settlement's `status` stays
    "pending" until ROSKYRO's internal team (the one actually receiving the
    money) independently confirms receipt via POST /{id}/confirm-received
    below. This prevents a partner from getting Marketing Fee credit just by
    claiming payment without ROSKYRO ever actually receiving it -- until
    that confirmation happens, this settlement shows as a pending task on
    both the partner's Wallet and ROSKYRO's internal Settlements page.

    An internal "mark paid" is a dispute-resolution override (the partner
    reported the payment through support instead of using the app) and
    finalizes the settlement immediately, bypassing the separate
    confirmation step -- ROSKYRO staff are vouching for the payment having
    happened, not self-reporting it."""
    settlement = await settlements.find_one({"_id": settlement_id})
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found.")

    is_payer_partner = current_user["appShell"] == "partner"
    if is_payer_partner:
        p = await partners.find_one({"org_id": current_user["orgId"]})
        is_payer_partner = bool(p) and p["_id"] == settlement["partner_id"]
    if not is_payer_partner and not is_internal(current_user["role"]):
        raise HTTPException(status_code=403, detail="Only the partner (who owes this Marketing Fee) or the ROSKYRO team can mark it paid.")

    if is_internal(current_user["role"]) and not is_payer_partner:
        # Dispute-resolution override: finalize immediately, no separate
        # confirmation step needed.
        update = {
            "status": "paid", "paid_at": now(),
            "payer_marked_paid_at": settlement.get("payer_marked_paid_at") or now(),
            "confirmed_by": "internal_override",
        }
        if body.paymentReference:
            update["payment_reference"] = body.paymentReference
        await settlements.update_one({"_id": settlement_id}, {"$set": update})
    else:
        if settlement.get("payer_marked_paid_at"):
            raise HTTPException(status_code=400, detail="Already marked paid — waiting for ROSKYRO to confirm receipt.")
        update = {"payer_marked_paid_at": now()}
        if body.paymentReference:
            update["payment_reference"] = body.paymentReference
        await settlements.update_one({"_id": settlement_id}, {"$set": update})

    updated = await settlements.find_one({"_id": settlement_id})
    await log_audit(current_user["id"], "settlement.marked_paid", "settlement", settlement_id, {"markedBy": current_user["appShell"], "hasPaymentReference": bool(body.paymentReference)})
    return {"settlement": to_out(updated)}


@router.post("/{settlement_id}/confirm-received")
async def confirm_received(settlement_id: str, current_user: dict = Depends(get_current_user)):
    """The other half of the two-sided confirmation: only ROSKYRO's
    internal team, as the actual recipient of the Marketing Fee, can
    confirm it was received, and only after the partner has claimed they
    paid. Only this confirmation finalizes the settlement to status "paid"
    -- until then it stays "pending" no matter what the payer clicked, per
    the rule that a payer's own claim is never enough on its own."""
    settlement = await settlements.find_one({"_id": settlement_id})
    if not settlement:
        raise HTTPException(status_code=404, detail="Settlement not found.")

    if not is_internal(current_user["role"]):
        raise HTTPException(status_code=403, detail="Only the ROSKYRO team can confirm receipt of a Marketing Fee.")
    if settlement["status"] == "paid":
        raise HTTPException(status_code=400, detail="This settlement is already confirmed as paid.")
    if not settlement.get("payer_marked_paid_at"):
        raise HTTPException(status_code=400, detail="The partner hasn't marked this as paid yet — nothing to confirm.")

    await settlements.update_one({"_id": settlement_id}, {"$set": {
        "status": "paid", "paid_at": now(), "confirmed_by": current_user["id"],
    }})
    updated = await settlements.find_one({"_id": settlement_id})
    await log_audit(current_user["id"], "settlement.confirmed_received", "settlement", settlement_id, {})
    return {"settlement": to_out(updated)}


DEFAULT_MARKETING_FEE_PAYOUT_PERCENTAGE = 20.0


async def _marketing_fee_payout_percentage() -> float:
    platform = await platform_settings.find_one({"_id": 1})
    if platform and platform.get("marketing_fee_payout_percentage") is not None:
        return float(platform["marketing_fee_payout_percentage"])
    return DEFAULT_MARKETING_FEE_PAYOUT_PERCENTAGE


@router.get("/marketing-fee-rate")
async def get_marketing_fee_rate():
    """The fixed % of collected Marketing Fees that ROSKYRO pays back out
    to a referring business, periodically, as a Marketing Fee Payout. Open
    to any authenticated user (customer dashboards show this so a business
    knows what cut they get back)."""
    return {"percentage": await _marketing_fee_payout_percentage()}


class MarketingFeeRateBody(BaseModel):
    percentage: float


@router.patch("/marketing-fee-rate", dependencies=[Depends(require_internal)])
async def set_marketing_fee_rate(body: MarketingFeeRateBody, current_user: dict = Depends(get_current_user)):
    if body.percentage < 0 or body.percentage > 100:
        raise HTTPException(status_code=400, detail="Percentage must be between 0 and 100.")
    await platform_settings.update_one(
        {"_id": 1},
        {"$set": {"marketing_fee_payout_percentage": body.percentage, "updated_at": now(), "updated_by": current_user["id"]}},
        upsert=True,
    )
    await log_audit(current_user["id"], "settings.marketing_fee_rate_updated", "platform_settings", None, {"percentage": body.percentage})
    return {"percentage": body.percentage}


async def _marketing_report_row(org: dict, period: str, rate: float) -> dict:
    """Every Marketing Fee collected from a partner (status: paid) whose
    referral was attributed to this referring business, for the given
    period, that hasn't already been folded into a finalized payout."""
    matching = await settlements.find({
        "org_id": org["_id"], "period_month": period, "status": "paid", "included_in_payout_id": None,
    }).to_list(None)
    total_collected = round(sum(float(s.get("amount") or 0) for s in matching), 2)
    payout_amount = round(total_collected * rate / 100, 2)
    existing_payout = await marketing_payouts.find_one({"org_id": org["_id"], "period": period})
    return {
        "org_id": org["_id"],
        "org_name": org.get("name"),
        "business_type": org.get("business_type"),
        "referral_count": len(matching),
        "total_fees_collected": total_collected,
        "payout_percentage": rate,
        "payout_amount": payout_amount,
        "payout_account_upi_id": org.get("marketing_payout_upi_id"),
        "payout_status": existing_payout.get("status") if existing_payout else ("not_generated" if total_collected > 0 else "nothing_collected"),
        "payout_id": existing_payout.get("_id") if existing_payout else None,
    }


@router.get("/marketing-report", dependencies=[Depends(require_internal)])
async def marketing_report(period: str = Query(..., description="YYYY-MM")):
    """ROSKYRO admin view: the complete list of every referring business
    that has generated at least one completed, Marketing-Fee-bearing
    referral, with that business's own data shown separately -- referral
    count, total Marketing Fees ROSKYRO collected because of them this
    period, the fixed-% payout that's calculated for them, and the account
    it should be sent to."""
    rate = await _marketing_fee_payout_percentage()
    org_ids = await settlements.distinct("org_id", {"period_month": period})
    rows = []
    for org_id in org_ids:
        org = await organizations.find_one({"_id": org_id})
        if not org:
            continue
        rows.append(await _marketing_report_row(org, period, rate))
    rows.sort(key=lambda r: -r["total_fees_collected"])
    return {"period": period, "payout_percentage": rate, "businesses": rows}


class CreatePayoutBody(BaseModel):
    orgId: str
    period: str


async def _next_invoice_number() -> str:
    n = await marketing_payouts.count_documents({})
    return f"MKT-INV-{str(n + 1).zfill(6)}"


@router.post("/marketing-payouts", status_code=201, dependencies=[Depends(require_internal)])
async def create_marketing_payout(body: CreatePayoutBody, current_user: dict = Depends(get_current_user)):
    """Finalizes this period's Marketing Fee Payout for one referring
    business: locks in the total collected, the rate, and the computed
    amount, snapshots the business's payout account, and marks every
    contributing settlement so it can never be double-counted into a later
    payout run."""
    org = await organizations.find_one({"_id": body.orgId})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found.")
    if await marketing_payouts.find_one({"org_id": body.orgId, "period": body.period}):
        raise HTTPException(status_code=400, detail="A payout for this business and period already exists.")

    rate = await _marketing_fee_payout_percentage()
    matching = await settlements.find({
        "org_id": body.orgId, "period_month": body.period, "status": "paid", "included_in_payout_id": None,
    }).to_list(None)
    total_collected = round(sum(float(s.get("amount") or 0) for s in matching), 2)
    if total_collected <= 0:
        raise HTTPException(status_code=400, detail="No collected Marketing Fees for this business in this period yet.")
    payout_amount = round(total_collected * rate / 100, 2)

    payout_id = new_id()
    doc = {
        "_id": payout_id, "invoice_number": await _next_invoice_number(),
        "org_id": body.orgId, "org_name": org.get("name"), "period": body.period,
        "referral_count": len(matching), "total_fees_collected": total_collected,
        "payout_percentage": rate, "payout_amount": payout_amount,
        "payout_account_upi_id": org.get("marketing_payout_upi_id"),
        "status": "pending", "paid_at": None,
        "created_by": current_user["id"], "created_at": now(),
    }
    await marketing_payouts.insert_one(doc)
    await settlements.update_many(
        {"_id": {"$in": [s["_id"] for s in matching]}},
        {"$set": {"included_in_payout_id": payout_id}},
    )
    await log_audit(current_user["id"], "marketing_payout.created", "marketing_payout", payout_id, {"orgId": body.orgId, "period": body.period, "amount": payout_amount})
    return {"payout": to_out(doc)}


@router.get("/marketing-payouts")
async def list_marketing_payouts(orgId: str | None = None, period: str | None = None, current_user: dict = Depends(get_current_user)):
    filt: dict = {}
    if current_user["appShell"] == "customer":
        filt["org_id"] = current_user["orgId"]
    elif not is_internal(current_user["role"]):
        raise HTTPException(status_code=403, detail="Not authorized.")
    elif orgId:
        filt["org_id"] = orgId
    if period:
        filt["period"] = period
    rows = await marketing_payouts.find(filt).sort("created_at", -1).to_list(None)
    return {"payouts": to_out_many(rows)}


@router.patch("/marketing-payouts/{payout_id}/mark-paid", dependencies=[Depends(require_internal)])
async def mark_marketing_payout_paid(payout_id: str, current_user: dict = Depends(get_current_user)):
    """ROSKYRO internal marks a Marketing Fee Payout as sent, once the UPI
    transfer to the referring business has actually been made outside the
    app -- same self-reported, ROSKYRO-vouches-for-it pattern used for the
    internal override on per-referral settlements above."""
    payout = await marketing_payouts.find_one({"_id": payout_id})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found.")
    if payout["status"] == "paid":
        raise HTTPException(status_code=400, detail="This payout is already marked paid.")
    await marketing_payouts.update_one({"_id": payout_id}, {"$set": {"status": "paid", "paid_at": now(), "paid_by": current_user["id"]}})
    updated = await marketing_payouts.find_one({"_id": payout_id})
    await log_audit(current_user["id"], "marketing_payout.marked_paid", "marketing_payout", payout_id, {})
    return {"payout": to_out(updated)}


@router.get("/marketing-payouts/{payout_id}/invoice")
async def marketing_payout_invoice(payout_id: str, current_user: dict = Depends(get_current_user)):
    """PDF invoice, in the referring business's name, documenting a single
    Marketing Fee Payout -- period covered, referral count, total fees
    ROSKYRO collected, the fixed %, the calculated payout amount, and the
    account it was (or will be) sent to."""
    payout = await marketing_payouts.find_one({"_id": payout_id})
    if not payout:
        raise HTTPException(status_code=404, detail="Payout not found.")
    if current_user["appShell"] == "customer" and current_user["orgId"] != payout["org_id"]:
        raise HTTPException(status_code=403, detail="Not authorized.")
    elif current_user["appShell"] not in ("customer", "internal"):
        raise HTTPException(status_code=403, detail="Not authorized.")

    # Same reasoning as appointments.py's daily PDF export: reportlab
    # rendering is synchronous CPU-bound work, so it runs in a worker
    # thread instead of blocking the event loop (and every other
    # concurrent request) for the duration of the render.
    pdf_bytes = await run_in_threadpool(render_marketing_payout_invoice_pdf, payout)
    filename = f"{payout['invoice_number']}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin-wallet", dependencies=[Depends(require_roles("roskyro_admin"))])
async def admin_wallet_summary(period: str = Query(..., description="YYYY-MM")):
    """The super-admin-only consolidated 'earnings wallet' view: every rupee
    that moved through ROSKYRO's two revenue streams for one calendar
    period, in one place.

    Two streams flow IN to ROSKYRO:
      - Marketing Fees a PARTNER pays for a completed referral (settlements
        collection, scoped by period_month).
      - Subscription renewal charges a BUSINESS pays for their own
        GROW/MANAGE/Networking Marketing/Complete plan (subscription_renewals
        collection, scoped by period).
    One stream flows OUT of ROSKYRO:
      - The Marketing Fee Payout ROSKYRO owes back to referring businesses --
        a fixed % of the Marketing Fees collected because of their referrals
        this period (same _marketing_report_row computation the existing
        internal Marketing Payouts page already uses).

    Each inflow is broken into collected (paid + confirmed) / awaiting the
    payer's own claim / claimed-but-not-yet-confirmed by ROSKYRO, so the
    dashboard shows not just what's landed but what's still moving through
    the two-sided confirmation pipeline. Everything here is scoped to a
    single `period` on purpose -- next month starts this same computation
    from zero again, exactly like the underlying settlements/subscription
    charges already do (nothing here is a running lifetime balance)."""

    # --- Subscription renewal charges for this period ---
    sub_charges = await subscription_renewals.find({"period": period}).to_list(None)
    sub_collected = [c for c in sub_charges if c["status"] == "paid"]
    sub_awaiting_confirmation = [c for c in sub_charges if c["status"] == "pending" and c.get("payer_marked_paid_at")]
    sub_awaiting_payment = [c for c in sub_charges if c["status"] == "pending" and not c.get("payer_marked_paid_at")]
    subscription_summary = {
        "collected_amount": round(sum(float(c.get("amount") or 0) for c in sub_collected), 2),
        "collected_count": len(sub_collected),
        "awaiting_confirmation_amount": round(sum(float(c.get("amount") or 0) for c in sub_awaiting_confirmation), 2),
        "awaiting_confirmation_count": len(sub_awaiting_confirmation),
        "awaiting_payment_amount": round(sum(float(c.get("amount") or 0) for c in sub_awaiting_payment), 2),
        "awaiting_payment_count": len(sub_awaiting_payment),
        "total_charged_amount": round(sum(float(c.get("amount") or 0) for c in sub_charges), 2),
        "total_charged_count": len(sub_charges),
    }

    # --- Marketing Fees partners owe ROSKYRO for this period ---
    mkt_settlements = await settlements.find({"period_month": period}).to_list(None)
    mkt_collected = [s for s in mkt_settlements if s["status"] == "paid"]
    mkt_awaiting_confirmation = [s for s in mkt_settlements if s["status"] == "pending" and s.get("payer_marked_paid_at")]
    mkt_awaiting_payment = [s for s in mkt_settlements if s["status"] == "pending" and not s.get("payer_marked_paid_at")]
    marketing_fees_summary = {
        "collected_amount": round(sum(float(s.get("amount") or 0) for s in mkt_collected), 2),
        "collected_count": len(mkt_collected),
        "awaiting_confirmation_amount": round(sum(float(s.get("amount") or 0) for s in mkt_awaiting_confirmation), 2),
        "awaiting_confirmation_count": len(mkt_awaiting_confirmation),
        "awaiting_payment_amount": round(sum(float(s.get("amount") or 0) for s in mkt_awaiting_payment), 2),
        "awaiting_payment_count": len(mkt_awaiting_payment),
        "total_charged_amount": round(sum(float(s.get("amount") or 0) for s in mkt_settlements), 2),
        "total_charged_count": len(mkt_settlements),
    }

    # --- Marketing Fee Payouts ROSKYRO owes OUT to referring businesses, business-wise ---
    rate = await _marketing_fee_payout_percentage()
    org_ids = await settlements.distinct("org_id", {"period_month": period})
    businesses = []
    for org_id in org_ids:
        org = await organizations.find_one({"_id": org_id})
        if not org:
            continue
        businesses.append(await _marketing_report_row(org, period, rate))
    businesses.sort(key=lambda r: -r["total_fees_collected"])

    # _marketing_report_row's total_fees_collected/payout_amount are a LIVE
    # sum over settlements not yet tagged into any payout
    # (included_in_payout_id: None) -- correct for "what would a new payout
    # generate right now", but once a business's payout for this period IS
    # generated, its contributing settlements get tagged and drop out of
    # that live sum, so the row recomputes to 0 even though the payout
    # itself (and its locked-in amount) still exists. Overlay the finalized
    # payout doc's own immutable total_fees_collected/payout_amount here so
    # a paid-out or pending-payout business still displays what it actually
    # was/will be paid, not a misleading 0.
    existing_payouts_this_period = await marketing_payouts.find({"period": period}).to_list(None)
    payout_doc_by_org = {p["org_id"]: p for p in existing_payouts_this_period}
    for b in businesses:
        payout_doc = payout_doc_by_org.get(b["org_id"])
        if payout_doc:
            b["total_fees_collected"] = payout_doc["total_fees_collected"]
            b["payout_amount"] = payout_doc["payout_amount"]

    already_paid_amount = round(sum(float(p["payout_amount"] or 0) for p in existing_payouts_this_period if p["status"] == "paid"), 2)
    already_paid_count = len([p for p in existing_payouts_this_period if p["status"] == "paid"])
    # "Pending to send" covers BOTH a payout already generated but not yet
    # marked paid (its amount is locked in on the payout doc) AND a business
    # with fees collected but no payout generated yet at all (its amount is
    # only a live estimate of what generating one now would produce).
    pending_generated = [p for p in existing_payouts_this_period if p["status"] != "paid"]
    pending_not_yet_generated = [b for b in businesses if b["payout_status"] == "not_generated" and b["payout_amount"] > 0]
    pending_to_send_amount = round(
        sum(float(p["payout_amount"] or 0) for p in pending_generated)
        + sum(b["payout_amount"] for b in pending_not_yet_generated),
        2,
    )
    pending_to_send_count = len(pending_generated) + len(pending_not_yet_generated)

    payouts_summary = {
        "businesses": businesses,
        "payout_percentage": rate,
        "already_paid_amount": already_paid_amount,
        "already_paid_count": already_paid_count,
        "pending_to_send_amount": pending_to_send_amount,
        "pending_to_send_count": pending_to_send_count,
    }

    total_collected_this_period = round(subscription_summary["collected_amount"] + marketing_fees_summary["collected_amount"], 2)
    wallet_summary = {
        "total_collected_this_period": total_collected_this_period,
        "already_paid_out_to_businesses": payouts_summary["already_paid_amount"],
        "pending_to_send_to_businesses": payouts_summary["pending_to_send_amount"],
        "net_after_payouts": round(total_collected_this_period - payouts_summary["already_paid_amount"] - payouts_summary["pending_to_send_amount"], 2),
    }

    return {
        "period": period,
        "subscription": subscription_summary,
        "marketing_fees": marketing_fees_summary,
        "marketing_fee_payouts": payouts_summary,
        "wallet": wallet_summary,
    }


@router.get("/statements")
async def list_statements(partyType: str | None = None, partyId: str | None = None, period: str | None = None, current_user: dict = Depends(get_current_user)):
    # Scope non-internal callers to their own party -- a business or partner
    # can only ever see their own financial statement, never one they pass
    # in via query params (this previously had no ownership check at all).
    if current_user["appShell"] == "customer":
        partyType, partyId = "org", current_user["orgId"]
    elif current_user["appShell"] == "partner":
        p = await partners.find_one({"org_id": current_user["orgId"]})
        partyType, partyId = "partner", (p["_id"] if p else "__none__")
    elif current_user["appShell"] != "internal":
        raise HTTPException(status_code=403, detail="Not authorized.")

    filt: dict = {}
    if partyType:
        filt["party_type"] = partyType
    if partyId:
        filt["party_id"] = partyId
    if period:
        filt["period_month"] = period
    rows = await statements.find(filt).sort("period_month", -1).to_list(None)
    return {"statements": to_out_many(rows)}

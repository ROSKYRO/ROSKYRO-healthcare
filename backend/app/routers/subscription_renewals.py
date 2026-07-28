"""Subscription renewal payment tracking + invoicing -- the same two-sided
pending -> business self-reports paid -> ROSKYRO confirms received ->
invoice lifecycle the Marketing Fee side already uses (settlements.py's
mark-paid/confirm-received, marketing_payouts' invoices), but for money
flowing the OTHER direction: a business owes ROSKYRO for its own
GROW/MANAGE/Networking Marketing/Complete subscription, not a partner
owing ROSKYRO a per-referral fee.

Deliberately scoped to RENEWALS only -- the very first billing period for
a subscription is still activated instantly via the existing "I've Paid --
Activate" checkout in routers/plans.py's /subscribe (unchanged). This
collection only ever covers the second period onward, so ROSKYRO's admin
team has to explicitly "Generate Renewal Charges" for a period (mirroring
POST /settlements/marketing-payouts being a deliberate per-period admin
action, not an automatic background job -- there's no billing gateway or
scheduler in this build).
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from app.db import subscription_renewals, organization_subscriptions, organizations, plans as plans_collection, users
from app.auth import get_current_user, require_internal, require_roles
from app.utils.roles import is_internal
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.ids import new_id, now, as_aware, to_out, to_out_many
from app.utils.invoices import render_subscription_renewal_invoice_pdf
from app.utils.counters import next_sequence

router = APIRouter(prefix="/api/subscription-renewals", tags=["subscription-renewals"], dependencies=[Depends(get_current_user)])


def _is_renewal_period_due(started_at, billing_cycle: str, period: str) -> bool:
    """True if `period` ("YYYY-MM") is a genuine RENEWAL period for a
    subscription that started at `started_at` -- i.e. strictly after the
    period it was first activated in (that first period was already paid
    for via the instant checkout in plans.py, never through this
    collection). Monthly subscriptions renew every month after the start
    month; yearly subscriptions renew once a year, in the same calendar
    month as the start, every year after the start year."""
    started_at = as_aware(started_at)
    p_year, p_month = int(period[:4]), int(period[5:7])
    if billing_cycle == "yearly":
        return p_month == started_at.month and p_year > started_at.year
    # monthly
    return (p_year, p_month) > (started_at.year, started_at.month)


async def _next_invoice_number() -> str:
    # Atomic $inc counter, not count_documents({}) -- see app/utils/counters.py.
    # This matters especially here: /generate loops over every active
    # subscription and used to call the old count-based version once per
    # subscription, making a full-collection scan repeat N times in a single
    # admin bulk action instead of running it (at most) once, ever.
    n = await next_sequence("subscription_renewal_invoice_number", bootstrap=lambda: subscription_renewals.count_documents({}))
    return f"SUB-INV-{str(n).zfill(6)}"


class GenerateBody(BaseModel):
    period: str  # "YYYY-MM"


@router.post("/generate", status_code=201, dependencies=[Depends(require_roles("roskyro_admin"))])
async def generate_renewal_charges(body: GenerateBody, current_user: dict = Depends(get_current_user)):
    """Bulk, idempotent: scans every ACTIVE subscription, and for each one
    whose billing cycle makes `body.period` a genuine renewal period,
    creates a pending charge -- unless one already exists for this
    subscription+period (safe to re-run for the same period; already-
    generated charges are just skipped, not duplicated or errored on)."""
    active_subs = await organization_subscriptions.find({"status": "active"}).to_list(None)

    # Batch-fetch everything the loop below needs via $in instead of a
    # find_one/find_one/find_one per subscription -- this used to make
    # POST /generate a 1 + up to 4*N query pattern for N active
    # subscriptions (already-generated check + org + plan + owner user),
    # which got slower purely from the platform's own subscriber growth.
    # Now it's a fixed handful of queries no matter how many subscriptions
    # are active.
    sub_ids = [s["_id"] for s in active_subs]
    org_ids = list({s["org_id"] for s in active_subs if s.get("org_id")})
    plan_codes = list({s["plan_code"] for s in active_subs if s.get("plan_code")})

    existing_renewals = await subscription_renewals.find(
        {"subscription_id": {"$in": sub_ids}, "period": body.period}
    ).to_list(None) if sub_ids else []
    existing_sub_ids = {r["subscription_id"] for r in existing_renewals}

    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}

    plan_docs = await plans_collection.find({"_id": {"$in": plan_codes}}).to_list(None) if plan_codes else []
    plans_by_code = {p["_id"]: p for p in plan_docs}

    owner_docs = await users.find({"org_id": {"$in": org_ids}, "role": "owner"}).to_list(None) if org_ids else []
    owner_by_org_id = {u["org_id"]: u for u in owner_docs}

    created, skipped = 0, 0
    for sub in active_subs:
        if not sub.get("started_at") or not sub.get("billing_cycle"):
            skipped += 1
            continue
        if not _is_renewal_period_due(sub["started_at"], sub["billing_cycle"], body.period):
            skipped += 1
            continue
        if sub["_id"] in existing_sub_ids:
            skipped += 1
            continue
        org = orgs_by_id.get(sub["org_id"])
        plan = plans_by_code.get(sub["plan_code"])
        charge_id = new_id()
        try:
            await subscription_renewals.insert_one({
                "_id": charge_id,
                "org_id": sub["org_id"], "org_name": org.get("name") if org else None,
                "subscription_id": sub["_id"], "plan_code": sub["plan_code"],
                "plan_name": plan.get("name") if plan else sub["plan_code"],
                "billing_cycle": sub["billing_cycle"], "period": body.period,
                "amount": sub.get("price_at_purchase") or 0,
                "invoice_number": await _next_invoice_number(),
                "status": "pending",
                "payer_marked_paid_at": None, "payment_reference": None,
                "confirmed_by": None, "paid_at": None,
                "created_by": current_user["id"], "created_at": now(),
            })
        except DuplicateKeyError:
            # Another concurrent "Generate Renewal Charges" call (or a
            # duplicate double-click) already created this subscription's
            # charge for this exact period between our upfront
            # existing_sub_ids check and this insert -- the unique index on
            # (subscription_id, period) is the actual backstop here, this
            # except just turns that race loss into a normal "skipped"
            # outcome instead of a raw 500.
            skipped += 1
            continue
        created += 1
        owner_user = owner_by_org_id.get(sub["org_id"])
        if owner_user:
            await notify(
                owner_user["_id"], "subscription_renewal_due",
                f"{plan.get('name') if plan else sub['plan_code']} renewal due",
                f"₹{sub.get('price_at_purchase') or 0} for {body.period} -- pay via UPI and mark it paid from Plans & Billing.",
                "subscription_renewal", charge_id,
            )

    await log_audit(current_user["id"], "subscription_renewals.generated", "subscription_renewal", None, {"period": body.period, "created": created, "skipped": skipped})
    return {"period": body.period, "created": created, "skipped": skipped}


@router.get("")
@router.get("/")
async def list_renewal_charges(period: str | None = None, orgId: str | None = None, current_user: dict = Depends(get_current_user)):
    filt: dict = {}
    if current_user["appShell"] == "customer":
        filt["org_id"] = current_user["orgId"]
    elif current_user["appShell"] == "partner":
        raise HTTPException(status_code=403, detail="Not applicable to partner accounts.")
    elif orgId:
        filt["org_id"] = orgId
    if period:
        filt["period"] = period
    rows = await subscription_renewals.find(filt).sort("created_at", -1).limit(300).to_list(None)
    return {"renewals": to_out_many(rows)}


class MarkPaidBody(BaseModel):
    paymentReference: str | None = None


@router.post("/{charge_id}/mark-paid")
async def mark_renewal_paid(charge_id: str, body: MarkPaidBody = MarkPaidBody(), current_user: dict = Depends(get_current_user)):
    """The business (the payer here) self-reports having paid -- same
    two-sided confirmation as settlements.py's mark-paid: this only records
    the business's own claim (`payer_marked_paid_at`, optional
    `payment_reference`); the charge's status stays "pending" until
    ROSKYRO's internal team independently confirms receipt via
    POST /{id}/confirm-received. An internal "mark paid" is a dispute-
    resolution override that finalizes immediately."""
    charge = await subscription_renewals.find_one({"_id": charge_id})
    if not charge:
        raise HTTPException(status_code=404, detail="Renewal charge not found.")

    is_payer_business = current_user["appShell"] == "customer" and current_user["orgId"] == charge["org_id"]
    if not is_payer_business and not is_internal(current_user["role"]):
        raise HTTPException(status_code=403, detail="Only the business (who owes this renewal) or the ROSKYRO team can mark it paid.")

    if is_internal(current_user["role"]) and not is_payer_business:
        update = {
            "status": "paid", "paid_at": now(),
            "payer_marked_paid_at": charge.get("payer_marked_paid_at") or now(),
            "confirmed_by": "internal_override",
        }
        if body.paymentReference:
            update["payment_reference"] = body.paymentReference
        await subscription_renewals.update_one({"_id": charge_id}, {"$set": update})
    else:
        if charge["status"] == "paid":
            raise HTTPException(status_code=400, detail="This renewal is already paid.")
        if charge.get("payer_marked_paid_at"):
            raise HTTPException(status_code=400, detail="Already marked paid — waiting for ROSKYRO to confirm receipt.")
        update = {"payer_marked_paid_at": now()}
        if body.paymentReference:
            update["payment_reference"] = body.paymentReference
        await subscription_renewals.update_one({"_id": charge_id}, {"$set": update})

    updated = await subscription_renewals.find_one({"_id": charge_id})
    await log_audit(current_user["id"], "subscription_renewal.marked_paid", "subscription_renewal", charge_id, {"markedBy": current_user["appShell"]})
    return {"renewal": to_out(updated)}


@router.post("/{charge_id}/confirm-received", dependencies=[Depends(require_internal)])
async def confirm_renewal_received(charge_id: str, current_user: dict = Depends(get_current_user)):
    """Only ROSKYRO internal, as the actual recipient of the subscription
    payment, can confirm it was received -- and only after the business has
    claimed they paid. Only this finalizes the charge to status "paid"."""
    charge = await subscription_renewals.find_one({"_id": charge_id})
    if not charge:
        raise HTTPException(status_code=404, detail="Renewal charge not found.")
    if charge["status"] == "paid":
        raise HTTPException(status_code=400, detail="This renewal is already confirmed as paid.")
    if not charge.get("payer_marked_paid_at"):
        raise HTTPException(status_code=400, detail="The business hasn't marked this as paid yet — nothing to confirm.")

    await subscription_renewals.update_one({"_id": charge_id}, {"$set": {
        "status": "paid", "paid_at": now(), "confirmed_by": current_user["id"],
    }})
    updated = await subscription_renewals.find_one({"_id": charge_id})
    await log_audit(current_user["id"], "subscription_renewal.confirmed_received", "subscription_renewal", charge_id, {})
    return {"renewal": to_out(updated)}


@router.get("/{charge_id}/invoice")
async def renewal_invoice(charge_id: str, current_user: dict = Depends(get_current_user)):
    charge = await subscription_renewals.find_one({"_id": charge_id})
    if not charge:
        raise HTTPException(status_code=404, detail="Renewal charge not found.")
    if current_user["appShell"] == "customer" and current_user["orgId"] != charge["org_id"]:
        raise HTTPException(status_code=403, detail="Not authorized.")
    elif current_user["appShell"] not in ("customer", "internal"):
        raise HTTPException(status_code=403, detail="Not authorized.")

    pdf_bytes = await run_in_threadpool(render_subscription_renewal_invoice_pdf, charge)
    filename = f"{charge['invoice_number']}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

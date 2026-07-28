"""Super-admin-only "Reset Demo Data" utility.

Why this exists: the live Team Dashboard on roskyro.in was showing seeded
demo numbers (9 Active Businesses, 5 Verified Partners, etc.) even though
no real client had been onboarded yet. Root cause: `python -m app.seed`
populates exactly this fake dataset (see app/seed.py's module docstring --
demo orgs like "Sunrise Family Clinic", demo partners, demo referrals, and
so on), and it was run at least once against the real production database
(most likely during initial setup/testing), leaving that data live. Added
per explicit product request so ROSKYRO can clear all of it in one
confirmed action and start onboarding real clients on a clean slate,
without having to touch anything via direct database access.

Scope, per explicit user decisions (see this round's conversation):
- CLEARED: every business/partner/referral/subscription/appointment/
  patient/task/notification/etc. record -- all demo OPERATIONAL data.
  Also clears contact_leads/newsletter_subscribers (explicitly requested,
  even though those could in principle hold a real visitor's submission --
  the user confirmed they want a totally clean start on these too).
- PRESERVED (real configuration, not demo data): the pricing catalog
  (plans/partner_plans), partner_categories (category taxonomy),
  platform_settings (UPI ID, Marketing Fee %), settlement_rules rows with
  scope "platform" or "category" (the already-configured default rates --
  only "partner"-scoped rate OVERRIDES are cleared, since those reference
  specific demo partners that are themselves being removed), and every
  ROSKYRO internal team account (role in ROSKYRO_ROLES) -- those aren't
  customer/partner data, they're the actual ROSKYRO team using this system.

This is IRREVERSIBLE (a hard delete_many, not a soft/undoable flag), so:
- GET /preview never deletes anything -- it returns exact per-collection
  counts of what a real run would remove, for the admin to review first.
  The in-app "Reset Demo Data" page calls this before showing the confirm
  step, so nobody triggers this blind.
- POST /run requires the exact confirmation phrase below in the request
  body -- a typo, a stray click, or a replayed request with an empty body
  can't accidentally trigger it.
"""
from fastapi import APIRouter, HTTPException, Depends

from app.db import (
    organizations, users, partners, partner_services, partner_agreements,
    referrals, referral_status_history, referral_followups,
    settlement_rules, settlements, statements, marketing_payouts,
    appointments, reviews, marketing_performance, visibility_score_history,
    approvals, notifications, tasks, team_performance, reports, audit_logs,
    organization_subscriptions, partner_subscriptions, subscription_renewals,
    booking_settings, patients, queue_entries, patient_followups, invoices,
    whatsapp_messages, doctors, contact_leads, newsletter_subscribers,
    password_reset_requests, partnerships, partnership_requests,
    booking_counters, sequence_counters,
)
from app.auth import get_current_user, require_roles
from app.utils.roles import ROSKYRO_ROLES
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/admin/reset-demo-data", tags=["admin"])

CONFIRM_PHRASE = "DELETE DEMO DATA"

# (label shown in the preview/results UI, collection, filter). filter={}
# clears the whole collection; `users` and `settlement_rules` only clear
# the demo-data SUBSET of the collection -- the rest of each is real
# configuration/accounts that must survive the reset.
_TARGETS = [
    ("Businesses", organizations, {}),
    ("Business & partner user accounts", users, {"role": {"$nin": ROSKYRO_ROLES}}),
    ("Partners", partners, {}),
    ("Partner services", partner_services, {}),
    ("Partner agreements", partner_agreements, {}),
    ("Referrals", referrals, {}),
    ("Referral status history", referral_status_history, {}),
    ("Referral follow-ups", referral_followups, {}),
    ("Partner-specific settlement rate overrides", settlement_rules, {"scope": "partner"}),
    ("Settlements", settlements, {}),
    ("Settlement statements", statements, {}),
    ("Marketing Fee payouts", marketing_payouts, {}),
    ("Appointments", appointments, {}),
    ("Reviews", reviews, {}),
    ("Marketing performance records", marketing_performance, {}),
    ("Visibility score history", visibility_score_history, {}),
    ("Approvals", approvals, {}),
    ("Notifications", notifications, {}),
    ("Tasks", tasks, {}),
    ("Team performance records", team_performance, {}),
    ("Reports", reports, {}),
    ("Audit log entries", audit_logs, {}),
    ("Business subscriptions", organization_subscriptions, {}),
    ("Partner subscriptions", partner_subscriptions, {}),
    ("Subscription renewal charges", subscription_renewals, {}),
    ("Booking settings", booking_settings, {}),
    ("Patients", patients, {}),
    ("Queue entries", queue_entries, {}),
    ("Patient follow-ups", patient_followups, {}),
    ("Invoices", invoices, {}),
    ("WhatsApp messages", whatsapp_messages, {}),
    ("Doctors", doctors, {}),
    ("Contact form leads", contact_leads, {}),
    ("Newsletter signups", newsletter_subscribers, {}),
    ("Password reset requests", password_reset_requests, {}),
    ("Partnerships", partnerships, {}),
    ("Partnership requests", partnership_requests, {}),
    ("Booking slot counters", booking_counters, {}),
    ("Sequence counters (referral/invoice numbers)", sequence_counters, {}),
]

PRESERVED_NOTE = (
    "Never touched: pricing catalog (GROW / MANAGE / Networking Marketing / "
    "Complete / Reels prices for both audiences), partner categories, UPI "
    "payment settings, Marketing Fee rate & category default rates, and "
    "every ROSKYRO internal team account."
)


@router.get("/preview", dependencies=[Depends(require_roles("roskyro_admin"))])
async def preview_reset_demo_data():
    """Read-only -- exact per-collection counts of what a real run would
    delete, without deleting anything. Always called before /run."""
    items = []
    total = 0
    for label, collection, filt in _TARGETS:
        count = await collection.count_documents(filt)
        items.append({"label": label, "count": count})
        total += count
    return {"items": items, "total": total, "preserved": PRESERVED_NOTE}


@router.post("/run", dependencies=[Depends(require_roles("roskyro_admin"))])
async def run_reset_demo_data(body: dict, current_user: dict = Depends(get_current_user)):
    """Irreversible. Requires body: {"confirm": "DELETE DEMO DATA"} typed
    exactly (case-sensitive, whitespace-trimmed) -- anything else is
    rejected with a 400 and nothing is touched."""
    if (body.get("confirm") or "").strip() != CONFIRM_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'Type "{CONFIRM_PHRASE}" exactly to confirm. Nothing was deleted.',
        )

    results = []
    total_deleted = 0
    for label, collection, filt in _TARGETS:
        result = await collection.delete_many(filt)
        results.append({"label": label, "deleted": result.deleted_count})
        total_deleted += result.deleted_count

    # audit_logs was itself just cleared above (it's in _TARGETS), so this
    # is intentionally the very first entry in the fresh log -- a durable
    # record of who reset the platform and exactly what was removed.
    await log_audit(current_user["id"], "admin.reset_demo_data", "platform", None, {
        "totalDeleted": total_deleted,
        "byCollection": {r["label"]: r["deleted"] for r in results},
    })
    return {"results": results, "totalDeleted": total_deleted}

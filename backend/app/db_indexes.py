"""Index creation for every collection that's actually queried by a
non-`_id` field somewhere in the routers (Mongo already auto-indexes
`_id`, so those lookups were never the problem).

Why this exists: with zero secondary indexes, every `find`/`find_one` on a
field like `org_id`, `email`, `referral_id` etc. forces Mongo to scan the
whole collection on every single request. That's invisible on a handful of
demo rows but gets steadily slower as real referrals/appointments/patients/
users accumulate in production -- the classic "site used to be fast, now
it's slow" story. `create_index` is idempotent (a repeat call with the same
spec is a no-op), so this is safe to run on every boot rather than only
once via a migration.

Runs for BOTH the mock DB (pytest, local dev with USE_MOCK_DB=true) and a
real MongoDB, from main.py's startup event -- mongomock-motor implements
`create_index` as a real (if simplified) operation, so this is exercised by
the test suite too, not just asserted to work in prod.

Deliberately does NOT change any query (no regex-to-exact-match rewrites,
no collation-based case-insensitive email indexes) -- that would alter
matching behavior and needs its own review. Plain indexes on the filtered
fields are a strictly additive, zero-risk win: same results, same code,
Mongo just no longer has to read every document to find them.
"""
from app.db import (
    users, organizations, partners, partner_categories, partner_services,
    referrals, referral_status_history, referral_followups,
    settlement_rules, settlements, marketing_payouts, statements,
    appointments, reviews, marketing_performance, visibility_score_history,
    approvals, notifications, tasks, reports, organization_subscriptions,
    booking_settings, patients, queue_entries, patient_followups, invoices,
    whatsapp_messages, partner_agreements, doctors, password_reset_requests,
    newsletter_subscribers, contact_leads, subscription_renewals,
    partnerships, partnership_requests,
)

# (collection, [index specs]) -- each spec is either a single field name
# (ascending index) or a list of (field, direction) tuples for a compound
# index. Grouped by collection in the same order routers reference them.
_INDEX_PLAN = [
    (users, ["email", "phone", "org_id", "role"]),
    (organizations, ["business_type", "status"]),
    (partners, ["org_id", "category_id", "verification_status", "is_available_now"]),
    (partner_categories, ["slug"]),
    (partner_services, ["partner_id"]),
    (partner_agreements, ["partner_id"]),
    (referrals, ["referring_org_id", "partner_id", "status", "created_at"]),
    (referral_status_history, ["referral_id"]),
    (referral_followups, ["referral_id"]),
    (settlement_rules, ["partner_id", "scope", "is_active", "category_id", "settlement_type"]),
    (settlements, ["org_id", "partner_id", "period_month", "status", "included_in_payout_id"]),
    (marketing_payouts, ["org_id", "period"]),
    (statements, [[("party_type", 1), ("party_id", 1)]]),
    # "booking_code" powers GET /appointments/lookup/{booking_code} --
    # the quick-referral flow's org-scoped exact-match lookup.
    (appointments, [[("org_id", 1), ("appointment_date", 1)], "patient_name", "booking_code"]),
    (reviews, ["org_id"]),
    (marketing_performance, [[("org_id", 1), ("period_month", 1)]]),
    (visibility_score_history, ["org_id"]),
    (approvals, [[("org_id", 1), ("status", 1)]]),
    (notifications, ["user_id"]),
    (tasks, ["assigned_to", "assigned_role", "status", "priority"]),
    (reports, ["org_id"]),
    (organization_subscriptions, [[("org_id", 1), ("status", 1)], [("org_id", 1), ("plan_code", 1)], "status"]),
    (subscription_renewals, [[("org_id", 1), ("period", 1)], [("subscription_id", 1), ("period", 1)], "status"]),
    (booking_settings, ["org_id"]),
    (patients, [[("org_id", 1), ("updated_at", -1)], "name", "phone"]),
    (queue_entries, [[("org_id", 1), ("checked_in_at", 1)]]),
    (patient_followups, [[("org_id", 1), ("patient_name", 1)]]),
    (invoices, [[("org_id", 1), ("status", 1)], "patient_name"]),
    # "status" added for the platform-wide (no org_id filter) WhatsApp
    # Queue view -- see routers/whatsapp.py's GET /queue.
    (whatsapp_messages, ["org_id", "referral_id", "patient_name", "status"]),
    (doctors, [[("org_id", 1), ("is_active", 1)]]),
    (password_reset_requests, [[("user_id", 1), ("status", 1)]]),
    (newsletter_subscribers, ["email"]),
    (contact_leads, ["created_at"]),
    # (org_id, category_id, status) covers both list_partnerships (org_id +
    # status="active") and _set_partnership's end-the-old-one update
    # (org_id + category_id + status="active") -- see routers/partnerships.py.
    (partnerships, [[("org_id", 1), ("category_id", 1), ("status", 1)], "partner_id"]),
    (partnership_requests, [[("org_id", 1), ("status", 1)], [("partner_id", 1), ("status", 1)]]),
]


async def ensure_indexes():
    for collection, specs in _INDEX_PLAN:
        for spec in specs:
            try:
                if isinstance(spec, str):
                    await collection.create_index(spec)
                else:
                    await collection.create_index(spec)
            except Exception:
                # Index creation is a pure performance optimization -- never
                # let a driver/version quirk on one index (or on the mock
                # DB) block app startup. Worst case that one lookup stays
                # at its previous (correct, just slower) collection-scan
                # behavior.
                pass

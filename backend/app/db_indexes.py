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
import logging

from app.db import (
    users, organizations, partners, partner_categories, partner_services,
    referrals, referral_status_history, referral_followups,
    settlement_rules, settlements, marketing_payouts, statements,
    appointments, reviews, marketing_performance, visibility_score_history,
    approvals, notifications, tasks, reports, organization_subscriptions,
    booking_settings, patients, queue_entries, patient_followups, invoices,
    whatsapp_messages, partner_agreements, doctors, password_reset_requests,
    newsletter_subscribers, contact_leads, subscription_renewals,
    partnerships, partnership_requests, partner_subscriptions,
)

logger = logging.getLogger(__name__)

# (collection, [index specs]) -- each spec is either a single field name
# (ascending index) or a list of (field, direction) tuples for a compound
# index. Grouped by collection in the same order routers reference them.
_INDEX_PLAN = [
    (users, ["email", "phone", "org_id", "role"]),
    # "created_at" and "name" back list_orgs's and org_directory's .sort()
    # calls in routers/orgs.py -- an unindexed sort forces Mongo to load
    # every matching document into memory before it can order and slice
    # to the first page, even though only up to 300 rows are ever returned.
    (organizations, ["business_type", "status", "created_at", "name"]),
    (partners, ["org_id", "category_id", "verification_status", "is_available_now"]),
    (partner_categories, ["slug"]),
    # "is_active" backs the AND-filter half of partners.py's
    # search_by_service (name regex + is_active=True) -- doesn't help the
    # regex itself (unanchored regex can't use an index either way, same
    # as this file's policy for other keyword-search fields) but lets
    # Mongo narrow on is_active before evaluating the regex.
    (partner_services, ["partner_id", "is_active"]),
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
    (partner_subscriptions, [[("org_id", 1), ("status", 1)], [("org_id", 1), ("plan_code", 1)], "status"]),
    # Plain "period" added for settlements.py's admin_wallet_summary,
    # which filters ONLY by period (no org_id/subscription_id prefix) --
    # the org_id compound index below and the UNIQUE (subscription_id,
    # period) index in _UNIQUE_INDEX_PLAN can't serve that query
    # efficiently since neither leads with "period" alone.
    #
    # NOTE: (subscription_id, period) is deliberately NOT listed here as a
    # second plain compound index -- it's created as a UNIQUE index in
    # _UNIQUE_INDEX_PLAN below instead (same key pattern also serves every
    # query this plain version would have), and creating both would collide:
    # Mongo (and mongomock) generate the same index name for the same key
    # pattern regardless of options, so the second create_index call with
    # unique=True would fail with an index-options conflict against the
    # first plain one -- silently, since ensure_indexes() below intentionally
    # swallows create_index errors. That silent failure is exactly what
    # happened here until this comment: the plain version below "won" (it
    # ran first, in this same loop) and the unique constraint never actually
    # took effect, defeating the entire point of _UNIQUE_INDEX_PLAN for this
    # collection.
    (subscription_renewals, [[("org_id", 1), ("period", 1)], "status", "period"]),
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

# UNIQUE indexes -- unlike everything in _INDEX_PLAN above (pure query
# speed, safe to lose silently), these are load-bearing for correctness:
# they're the actual duplicate-prevention backstop for two known
# check-then-insert race conditions (two concurrent requests can both pass
# an in-app "does this already exist?" check before either one's insert
# lands), each paired with a try/except DuplicateKeyError at the insert
# site that turns the DB's rejection into a normal "already exists"
# response instead of a second row:
#   - subscription_renewals: (subscription_id, period) -- generate_renewal_
#     charges (subscription_renewals.py) loops over every active
#     subscription and inserts one renewal charge per (subscription,
#     period); two concurrent "Generate Renewal Charges" calls for the
#     same period would otherwise both insert a charge for the same
#     subscription, double-billing that business for the period.
#   - settlements: referral_id -- transition_referral (referrals.py) only
#     ever creates one settlement per completed referral; this is the
#     backstop behind that endpoint's own compare-and-set status guard.
#   - partnerships: (org_id, category_id) WHERE status="active" (a partial
#     index -- see the partialFilterExpression kwarg below) -- _set_
#     partnership (partnerships.py) ends whatever partnership was active
#     for this (org_id, category_id) before inserting the new one; two
#     concurrent "set my partner for this category" calls (a double-click,
#     or a request retried after a slow/timed-out response) could otherwise
#     both pass that same end-the-old-one step and both insert an active
#     row, leaving two simultaneously "active" partnerships for one
#     category -- silently breaking the "at most one active partnership
#     per (org, category)" invariant this whole file's module docstring
#     promises. Deliberately partial (scoped to status="active" only) since
#     a business's ENDED/historical partnerships for the same category are
#     expected and must NOT collide with each other or with the current
#     active one -- a plain (non-partial) unique index here would reject
#     the second partnership ever set for a given category, not just a
#     genuine concurrent duplicate.
# NOTE: if unique index creation itself ever fails (e.g. pre-existing
# duplicate rows in an already-corrupted real database), this same
# try/except swallows that failure silently too -- the app still boots,
# but the duplicate-prevention guard would then be missing. A real
# deployment should monitor startup logs (or add an explicit index-health
# check) rather than assume this is bulletproof.
_UNIQUE_INDEX_PLAN = [
    (subscription_renewals, [("subscription_id", 1), ("period", 1)], {}),
    (settlements, [("referral_id", 1)], {}),
    (partnerships, [("org_id", 1), ("category_id", 1)], {"partialFilterExpression": {"status": "active"}}),
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

    for collection, spec, extra_kwargs in _UNIQUE_INDEX_PLAN:
        try:
            await collection.create_index(spec, unique=True, **extra_kwargs)
        except Exception:
            # See the note above _UNIQUE_INDEX_PLAN -- still never block
            # startup (a real deployment shouldn't crash-loop over an index
            # quirk), but log this one loudly: unlike the plain-index loop
            # above, a failure here means a correctness backstop (duplicate-
            # prevention) is silently missing, not just a slower query. This
            # is exactly the class of bug that let a same-key-pattern plain
            # index in _INDEX_PLAN silently shadow this unique index until
            # it was caught by a direct DuplicateKeyError test -- logging
            # here means the NEXT such conflict shows up in startup logs
            # instead of only being discoverable by testing the race itself.
            logger.warning(
                "Failed to create UNIQUE index %s on %s -- duplicate-prevention "
                "guard for this collection may be missing. Check for a "
                "conflicting plain index with the same key pattern.",
                spec, collection.name, exc_info=True,
            )
            # query.
            pass

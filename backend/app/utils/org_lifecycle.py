"""Round 24: org-level account lifecycle for ROSKYRO's super admin dashboard
-- activate/deactivate is a simple `is_suspended` flip (see auth.py's
get_current_user, which locks out every user of a suspended org), but hard
delete has to reach every collection that stores a business's or partner's
data. There is no cascading-delete feature anywhere else in this codebase to
build on, so this enumerates every org_id/partner_id-scoped collection by
hand -- deliberately over-inclusive (an empty delete_many on an unrelated
collection is a no-op) rather than risk leaving orphaned rows behind after a
"permanent" delete.

Two org "kinds" share the same `organizations` collection row:
  - a business: has its own users/doctors/appointments/etc keyed by org_id.
  - a partner: ALSO has a `partners` collection row (org_id -> partner._id),
    and a partner's own data (services, agreements, settlement rules,
    inbound referrals/settlements) is keyed by that partner_id instead.
A single org can only be one or the other in practice (is_partner flag), but
this cascades both org_id-keyed and (if applicable) partner_id-keyed data so
nothing is left behind either way.
"""
from app.db import (
    organizations, users, doctors, appointments, booking_settings, patients,
    queue_entries, patient_followups, invoices, whatsapp_messages,
    organization_subscriptions, partner_subscriptions, subscription_renewals,
    reviews, marketing_performance, visibility_score_history, approvals,
    tasks, reports, referrals, referral_status_history, referral_followups,
    partnerships, partnership_requests, marketing_payouts, settlements,
    settlement_rules, statements, notifications, partners, partner_services,
    partner_agreements,
)
from app.utils.ids import now


async def deactivate_org(org_id: str, admin_id: str) -> None:
    await organizations.update_one(
        {"_id": org_id},
        {"$set": {"is_suspended": True, "suspended_at": now(), "suspended_by": admin_id}},
    )


async def activate_org(org_id: str) -> None:
    await organizations.update_one(
        {"_id": org_id},
        {"$set": {"is_suspended": False, "suspended_at": None, "suspended_by": None}},
    )


async def hard_delete_org(org_id: str) -> dict:
    """Permanently erase this org and every row anywhere in the database
    that belongs to it. Returns a counts summary for the audit log --
    called BEFORE the org doc itself is deleted, so the caller can log the
    org's name/type first."""
    user_rows = await users.find({"org_id": org_id}, {"_id": 1}).to_list(None)
    user_ids = [u["_id"] for u in user_rows]

    partner_doc = await partners.find_one({"org_id": org_id})
    partner_id = partner_doc["_id"] if partner_doc else None

    referral_filter = {"referring_org_id": org_id}
    if partner_id:
        referral_filter = {"$or": [{"referring_org_id": org_id}, {"partner_id": partner_id}]}
    referral_rows = await referrals.find(referral_filter, {"_id": 1}).to_list(None)
    referral_ids = [r["_id"] for r in referral_rows]

    counts = {}

    async def _delete(collection, filt, label):
        result = await collection.delete_many(filt)
        counts[label] = result.deleted_count

    # org_id-keyed collections (business's own data -- also present, but
    # empty, for a partner-type org since a partner rarely runs its own
    # patient/appointment book, though nothing stops it from doing so).
    await _delete(doctors, {"org_id": org_id}, "doctors")
    await _delete(appointments, {"org_id": org_id}, "appointments")
    await _delete(booking_settings, {"org_id": org_id}, "booking_settings")
    await _delete(patients, {"org_id": org_id}, "patients")
    await _delete(queue_entries, {"org_id": org_id}, "queue_entries")
    await _delete(patient_followups, {"org_id": org_id}, "patient_followups")
    await _delete(invoices, {"org_id": org_id}, "invoices")
    await _delete(whatsapp_messages, {"org_id": org_id}, "whatsapp_messages")
    await _delete(organization_subscriptions, {"org_id": org_id}, "organization_subscriptions")
    await _delete(partner_subscriptions, {"org_id": org_id}, "partner_subscriptions")
    await _delete(subscription_renewals, {"org_id": org_id}, "subscription_renewals")
    await _delete(reviews, {"org_id": org_id}, "reviews")
    await _delete(marketing_performance, {"org_id": org_id}, "marketing_performance")
    await _delete(visibility_score_history, {"org_id": org_id}, "visibility_score_history")
    await _delete(approvals, {"org_id": org_id}, "approvals")
    await _delete(tasks, {"org_id": org_id}, "tasks")
    await _delete(reports, {"org_id": org_id}, "reports")
    await _delete(marketing_payouts, {"org_id": org_id}, "marketing_payouts")

    partnership_filter = {"org_id": org_id}
    partnership_request_filter = {"org_id": org_id}
    settlement_filter = {"org_id": org_id}
    if partner_id:
        partnership_filter = {"$or": [{"org_id": org_id}, {"partner_id": partner_id}]}
        partnership_request_filter = {"$or": [{"org_id": org_id}, {"partner_id": partner_id}]}
        settlement_filter = {"$or": [{"org_id": org_id}, {"partner_id": partner_id}]}
    await _delete(partnerships, partnership_filter, "partnerships")
    await _delete(partnership_requests, partnership_request_filter, "partnership_requests")
    await _delete(settlements, settlement_filter, "settlements")

    if referral_ids:
        await _delete(referral_status_history, {"referral_id": {"$in": referral_ids}}, "referral_status_history")
        await _delete(referral_followups, {"referral_id": {"$in": referral_ids}}, "referral_followups")
    await _delete(referrals, referral_filter, "referrals")

    # statements has no live writer today (dead-but-defined collection), kept
    # here in case that changes -- covers both a business's own statements
    # (party_type "business") and a partner's (party_type "partner").
    statement_ids = [org_id] + ([partner_id] if partner_id else [])
    await _delete(statements, {"party_id": {"$in": statement_ids}}, "statements")

    if partner_id:
        await _delete(settlement_rules, {"partner_id": partner_id}, "settlement_rules")
        await _delete(partner_services, {"partner_id": partner_id}, "partner_services")
        await _delete(partner_agreements, {"partner_id": partner_id}, "partner_agreements")
        await _delete(partners, {"_id": partner_id}, "partners")

    if user_ids:
        await _delete(notifications, {"user_id": {"$in": user_ids}}, "notifications")
    await _delete(users, {"org_id": org_id}, "users")

    await organizations.delete_one({"_id": org_id})
    counts["organizations"] = 1
    return counts

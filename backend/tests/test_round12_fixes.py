"""Regression tests for round 12's fixes:

1. settlements.py's POST /rules (the generic admin settlement-rule
   endpoint) only deactivated a pre-existing active rule for scope=
   "category" -- for "partner"/"org"/"org_partner_pair" it inserted a new
   active row unconditionally, so an admin override for a partner who
   already has an active rule (e.g. self-set via PUT /my-rate, or
   seeded) left TWO simultaneously-active rows for the same target.
   transition_referral's resolution loop (referrals.py) does a plain
   find_one({..., "is_active": True}) with no sort, so which rule applied
   -- and therefore what Marketing Fee got charged -- was
   non-deterministic. Fixed by deactivating the same-target active row for
   every scope, not just "category".

2. settlements.py's POST /rules didn't require the scope's matching id(s)
   for "org"/"partner"/"org_partner_pair" (only "category" was validated),
   silently creating an inert, never-matchable rule. Fixed by requiring
   orgId/partnerId per scope.

3. settlements.py's POST /marketing-payouts had a check-then-insert race
   with no backing unique index -- two concurrent calls for the same
   org+period could both pass the "does a payout already exist" check and
   both insert, double-paying a business for one period. Fixed with a
   unique (org_id, period) index (db_indexes.py) + a DuplicateKeyError
   catch that turns the race into the same clean 400 the sequential check
   already gives.

4. referrals.py's transition_referral incremented a partner's
   total_referrals_completed counter on the "report_uploaded" status
   instead of "completed" -- since report_uploaded's only next step is
   completed (and a referral can sit at report_uploaded indefinitely),
   this over-credited partners for referrals that were never actually
   finished. This counter feeds directly into partners.py's AI-score
   partner ranking. Fixed by moving the increment into the "completed"
   branch.
"""
import pytest
from pymongo.errors import DuplicateKeyError

DEMO_PASSWORD = "Roskyro@123"
PARTNER_ADMIN_EMAIL = "admin.cityscan.diagnostics@example.com"  # seeded with an active scope="partner" rule
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# ---------------------------------------------------------------------------
# settlements.py -- create_rule() dedup gap
# ---------------------------------------------------------------------------

def test_create_rule_deactivates_existing_active_partner_rule(client, admin_headers):
    """CityScan Diagnostics is seeded with an already-active scope="partner"
    rule (app/seed.py). Creating a NEW admin override for that same
    partner_id via POST /rules must deactivate the old one -- not leave
    two simultaneously active."""
    partner_headers = _login(client, PARTNER_ADMIN_EMAIL)
    my_rate = client.get("/api/settlements/my-rate", headers=partner_headers)
    assert my_rate.status_code == 200, my_rate.text
    existing_rule = my_rate.json()["rate"]
    assert existing_rule is not None, "expected CityScan to already have an active partner-scope rule"
    partner_id = existing_rule["partner_id"]

    resp = client.post("/api/settlements/rules", headers=admin_headers, json={
        "scope": "partner", "partnerId": partner_id, "settlementType": "flat_fee", "flatFeeAmount": 999,
    })
    assert resp.status_code == 201, resp.text

    all_rules = client.get("/api/settlements/rules", headers=admin_headers)
    assert all_rules.status_code == 200, all_rules.text
    active_for_partner = [
        r for r in all_rules.json()["rules"]
        if r["scope"] == "partner" and r["partner_id"] == partner_id and r["is_active"]
    ]
    assert len(active_for_partner) == 1, f"expected exactly 1 active partner rule, found {len(active_for_partner)}"
    assert active_for_partner[0]["flat_fee_amount"] == 999


def test_create_rule_requires_matching_id_for_partner_scope(client, admin_headers):
    resp = client.post("/api/settlements/rules", headers=admin_headers, json={
        "scope": "partner", "settlementType": "flat_fee", "flatFeeAmount": 100,
    })
    assert resp.status_code == 400, resp.text
    assert "partnerid" in resp.json()["error"].lower()


def test_create_rule_requires_matching_id_for_org_scope(client, admin_headers):
    resp = client.post("/api/settlements/rules", headers=admin_headers, json={
        "scope": "org", "settlementType": "flat_fee", "flatFeeAmount": 100,
    })
    assert resp.status_code == 400, resp.text
    assert "orgid" in resp.json()["error"].lower()


def test_create_rule_requires_both_ids_for_org_partner_pair_scope(client, admin_headers):
    resp = client.post("/api/settlements/rules", headers=admin_headers, json={
        "scope": "org_partner_pair", "settlementType": "flat_fee", "flatFeeAmount": 100,
    })
    assert resp.status_code == 400, resp.text


# ---------------------------------------------------------------------------
# settlements.py -- create_marketing_payout() TOCTOU
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_marketing_payouts_unique_index_prevents_duplicate_payout():
    """Direct DB-level test (per this engagement's established methodology
    for TOCTOU fixes -- mongomock + single-process asyncio tends to fully
    serialize what would be a genuine race under real concurrent load, so
    a live concurrent-request test wouldn't reliably reproduce the race;
    the unique index itself is the actual backstop and is what must be
    verified directly)."""
    from app.db import marketing_payouts
    from app.utils.ids import now

    base = {
        "org_id": "test-round12-org-async", "org_name": "Test Org", "period": "2099-02",
        "referral_count": 1, "total_fees_collected": 100.0,
        "payout_percentage": 10, "payout_amount": 10.0,
        "payout_account_upi_id": None, "status": "pending", "paid_at": None,
        "created_by": "test", "created_at": now(),
    }
    await marketing_payouts.insert_one({**base, "_id": "test-round12-payout-a", "invoice_number": "MKT-INV-TESTA"})
    try:
        with pytest.raises(DuplicateKeyError):
            await marketing_payouts.insert_one({**base, "_id": "test-round12-payout-b", "invoice_number": "MKT-INV-TESTB"})
    finally:
        # Cleanup so this synthetic row doesn't pollute other tests sharing
        # this session-scoped in-memory DB.
        await marketing_payouts.delete_many({"org_id": "test-round12-org-async"})


# ---------------------------------------------------------------------------
# referrals.py -- total_referrals_completed counted on the wrong status
# ---------------------------------------------------------------------------

def _cityscan_partner_id(client, headers):
    resp = client.get("/api/partners", headers=headers)
    assert resp.status_code == 200, resp.text
    for p in resp.json()["partners"]:
        if p.get("org_name") == "CityScan Diagnostics" and p.get("verification_status") == "verified":
            return p["id"]
    raise AssertionError("expected the seeded verified 'CityScan Diagnostics' partner")


def _get_completed_count(client, headers, partner_id):
    resp = client.get(f"/api/partners/{partner_id}", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["partner"]["total_referrals_completed"]


def test_report_uploaded_does_not_increment_completed_counter(client, admin_headers):
    """A referral that reaches report_uploaded but is never actually
    marked completed must NOT count toward the partner's
    total_referrals_completed -- only actually completing it should. This
    is the real bug: report_uploaded's only next transition IS completed
    (see TRANSITIONS in referrals.py), so a referral can sit at
    report_uploaded indefinitely, and pre-fix it was already counted as
    done at that point."""
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    partner_headers = _login(client, PARTNER_ADMIN_EMAIL)
    partner_id = _cityscan_partner_id(client, sunrise_headers)

    before = _get_completed_count(client, admin_headers, partner_id)

    created = client.post("/api/referrals", headers=sunrise_headers, json={
        "partnerId": partner_id, "patientName": "Round12 Counter Test Patient",
        "serviceRequested": "Round 12 counter regression test",
    })
    assert created.status_code == 201, created.text
    referral_id = created.json()["referral"]["id"]

    for status in ("accepted", "in_progress", "report_uploaded"):
        resp = client.post(f"/api/referrals/{referral_id}/transition", headers=partner_headers, json={"status": status})
        assert resp.status_code == 200, resp.text

    # Stopped at report_uploaded -- must NOT have incremented the counter.
    after_report_uploaded = _get_completed_count(client, admin_headers, partner_id)
    assert after_report_uploaded == before, (
        "report_uploaded must not increment total_referrals_completed "
        f"(before={before}, after={after_report_uploaded})"
    )

    # Now actually complete it -- THIS must increment the counter.
    resp = client.post(f"/api/referrals/{referral_id}/transition", headers=sunrise_headers, json={"status": "completed"})
    assert resp.status_code == 200, resp.text
    after_completed = _get_completed_count(client, admin_headers, partner_id)
    assert after_completed == before + 1, (
        f"completed must increment total_referrals_completed by exactly 1 (before={before}, after={after_completed})"
    )

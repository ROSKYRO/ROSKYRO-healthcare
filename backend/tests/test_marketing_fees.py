"""Tests for the Marketing Fee model pivot: a completed patient referral is
treated as marketing the referring business did for the partner, so the
per-referral fee is owed by the PARTNER to ROSKYRO (not to the referring
business), and ROSKYRO periodically pays a fixed % of what it collects back
to the referring business as a Marketing Fee Payout, with an invoice.

Rather than lean on the exact shape of seeded demo settlements (fragile --
their pending/marked state can be mutated by other tests sharing the same
session-scoped DB), each test here drives its own referral from creation
through to "completed" so it owns a dedicated, freshly-generated
settlement."""
from datetime import datetime, timezone

DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # clinic -- eligible to create referrals
CITYSCAN_PARTNER_ADMIN_EMAIL = "admin.cityscan.diagnostics@example.com"  # verified seeded partner


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _cityscan_partner_id(client, headers):
    """The partner id for the seeded, verified 'CityScan Diagnostics' --
    matched to CITYSCAN_PARTNER_ADMIN_EMAIL's org specifically, so the
    partner-side transitions/mark-paid calls in these tests act on a
    referral actually sent to that partner (not some other seeded
    verified partner)."""
    resp = client.get("/api/partners", headers=headers)
    assert resp.status_code == 200, resp.text
    for p in resp.json()["partners"]:
        if p.get("org_name") == "CityScan Diagnostics" and p.get("verification_status") == "verified":
            return p["id"]
    raise AssertionError("expected the seeded verified 'CityScan Diagnostics' partner")


def _complete_new_referral(client, sunrise_headers, partner_headers, admin_headers, partner_id, patient_name):
    """Creates a referral from Sunrise -> the given (verified) partner and
    drives it all the way to "completed", returning the resulting
    settlement (or None if the resolved rule was "none").

    Fetches the resulting settlement via `admin_headers` (internal), not the
    referring business's own headers -- the business is intentionally
    forbidden from GET /api/settlements (see
    test_business_cannot_see_settlement_fee_details below), so internal is
    the only role here guaranteed to see every settlement regardless of
    which partner it's against."""
    created = client.post("/api/referrals", headers=sunrise_headers, json={
        "partnerId": partner_id,
        "patientName": patient_name,
        "serviceRequested": "Marketing Fee Test Service",
    })
    assert created.status_code == 201, created.text
    referral_id = created.json()["referral"]["id"]
    assert created.json()["referral"]["status"] == "sent"  # verified partner -> no review gate

    for status in ("accepted", "in_progress", "report_uploaded"):
        resp = client.post(f"/api/referrals/{referral_id}/transition", headers=partner_headers, json={"status": status})
        assert resp.status_code == 200, resp.text

    resp = client.post(f"/api/referrals/{referral_id}/transition", headers=sunrise_headers, json={"status": "completed"})
    assert resp.status_code == 200, resp.text

    settlements = client.get("/api/settlements", headers=admin_headers).json()["settlements"]
    return next((s for s in settlements if s["referral_id"] == referral_id), None)


def test_business_cannot_see_settlement_fee_details(client, admin_headers):
    """The referring business's dashboard shows only referral status/
    tracking (which partner accepted/completed it) -- never the Marketing
    Fee amounts a partner owes/paid ROSKYRO. GET /api/settlements and
    /api/settlements/rules must reject the customer role outright, while
    staying open to the partner (the actual payer) and ROSKYRO internal."""
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    partner_headers = _login(client, CITYSCAN_PARTNER_ADMIN_EMAIL)

    forbidden = client.get("/api/settlements", headers=sunrise_headers)
    assert forbidden.status_code == 403, forbidden.text

    forbidden_rules = client.get("/api/settlements/rules", headers=sunrise_headers)
    assert forbidden_rules.status_code == 403, forbidden_rules.text

    # partner and internal are unaffected
    assert client.get("/api/settlements", headers=partner_headers).status_code == 200
    assert client.get("/api/settlements", headers=admin_headers).status_code == 200


def test_partner_is_payer_and_only_internal_confirms_receipt(client, admin_headers):
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    partner_headers = _login(client, CITYSCAN_PARTNER_ADMIN_EMAIL)
    partner_id = _cityscan_partner_id(client, sunrise_headers)

    settlement = _complete_new_referral(client, sunrise_headers, partner_headers, admin_headers, partner_id, "Marketing Fee Test Patient 1")
    assert settlement, "expected a settlement rule to apply for this seeded verified partner"
    settlement_id = settlement["id"]

    # The referring business is no longer the payer -- it must NOT be able
    # to mark this paid.
    resp = client.post(f"/api/settlements/{settlement_id}/mark-paid", headers=sunrise_headers)
    assert resp.status_code == 403, resp.text

    # The partner (the actual payer, owing a Marketing Fee to ROSKYRO) can.
    marked = client.post(f"/api/settlements/{settlement_id}/mark-paid", headers=partner_headers)
    assert marked.status_code == 200, marked.text
    assert marked.json()["settlement"]["payer_marked_paid_at"]

    # Partner (the payer) cannot confirm its own receipt -- only ROSKYRO can.
    resp = client.post(f"/api/settlements/{settlement_id}/confirm-received", headers=partner_headers)
    assert resp.status_code == 403, resp.text

    confirmed = client.post(f"/api/settlements/{settlement_id}/confirm-received", headers=admin_headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["settlement"]["status"] == "paid"


def test_marketing_fee_rate_config(client, admin_headers):
    # The whole /api/settlements router requires auth -- "open to any
    # authenticated user" (per the endpoint's docstring) still needs a
    # bearer token, just not an internal one.
    sunrise_headers = _login(client, SUNRISE_EMAIL)

    resp = client.get("/api/settlements/marketing-fee-rate", headers=sunrise_headers)
    assert resp.status_code == 200, resp.text
    original = resp.json()["percentage"]

    # a non-internal user cannot change the rate
    forbidden = client.patch("/api/settlements/marketing-fee-rate", headers=sunrise_headers, json={"percentage": 25})
    assert forbidden.status_code == 403, forbidden.text

    resp = client.patch("/api/settlements/marketing-fee-rate", headers=admin_headers, json={"percentage": 25})
    assert resp.status_code == 200, resp.text
    assert resp.json()["percentage"] == 25

    resp = client.get("/api/settlements/marketing-fee-rate", headers=sunrise_headers)
    assert resp.json()["percentage"] == 25

    # restore for other tests in this session-scoped DB
    client.patch("/api/settlements/marketing-fee-rate", headers=admin_headers, json={"percentage": original})


def test_marketing_report_and_payout_and_invoice(client, admin_headers):
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    partner_headers = _login(client, CITYSCAN_PARTNER_ADMIN_EMAIL)
    partner_id = _cityscan_partner_id(client, sunrise_headers)

    me = client.get("/api/auth/me", headers=sunrise_headers).json()["user"]
    org_id = me["orgId"]

    resp = client.patch(f"/api/orgs/{org_id}", headers=sunrise_headers, json={"marketingPayoutUpiId": "sunrise.pytest@okhdfcbank"})
    assert resp.status_code == 200, resp.text

    settlement = _complete_new_referral(client, sunrise_headers, partner_headers, admin_headers, partner_id, "Marketing Fee Test Patient 2")
    assert settlement, "expected a settlement rule to apply for this seeded verified partner"

    # fully settle it (partner pays, internal confirms) so the report has a
    # non-zero "paid" total to work with
    client.post(f"/api/settlements/{settlement['id']}/mark-paid", headers=partner_headers)
    client.post(f"/api/settlements/{settlement['id']}/confirm-received", headers=admin_headers)

    period = datetime.now(timezone.utc).strftime("%Y-%m")
    report = client.get("/api/settlements/marketing-report", headers=admin_headers, params={"period": period})
    assert report.status_code == 200, report.text
    row = next((r for r in report.json()["businesses"] if r["org_id"] == org_id), None)
    assert row, "expected Sunrise Family Clinic in the marketing report"
    assert row["total_fees_collected"] > 0
    assert row["payout_amount"] == round(row["total_fees_collected"] * row["payout_percentage"] / 100, 2)

    # non-internal cannot see the report
    forbidden = client.get("/api/settlements/marketing-report", headers=sunrise_headers, params={"period": period})
    assert forbidden.status_code == 403, forbidden.text

    payout = client.post("/api/settlements/marketing-payouts", headers=admin_headers, json={"orgId": org_id, "period": period})
    assert payout.status_code == 201, payout.text
    payout_id = payout.json()["payout"]["id"]
    assert payout.json()["payout"]["payout_amount"] == row["payout_amount"]

    # duplicate payout for the same org+period is rejected
    dup = client.post("/api/settlements/marketing-payouts", headers=admin_headers, json={"orgId": org_id, "period": period})
    assert dup.status_code == 400, dup.text

    # the business can see and download its own invoice
    invoice = client.get(f"/api/settlements/marketing-payouts/{payout_id}/invoice", headers=sunrise_headers)
    assert invoice.status_code == 200, invoice.text
    assert invoice.headers["content-type"] == "application/pdf"
    assert invoice.content[:5] == b"%PDF-"

    mark = client.patch(f"/api/settlements/marketing-payouts/{payout_id}/mark-paid", headers=admin_headers)
    assert mark.status_code == 200, mark.text
    assert mark.json()["payout"]["status"] == "paid"

    listed = client.get("/api/settlements/marketing-payouts", headers=sunrise_headers)
    assert listed.status_code == 200, listed.text
    assert any(p["id"] == payout_id for p in listed.json()["payouts"])


def test_org_payout_upi_field_roundtrips(client):
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    me = client.get("/api/auth/me", headers=sunrise_headers).json()["user"]
    org_id = me["orgId"]

    resp = client.patch(f"/api/orgs/{org_id}", headers=sunrise_headers, json={"marketingPayoutUpiId": "roundtrip.test@okaxis"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["organization"]["marketing_payout_upi_id"] == "roundtrip.test@okaxis"

    fetched = client.get(f"/api/orgs/{org_id}", headers=sunrise_headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["organization"]["marketing_payout_upi_id"] == "roundtrip.test@okaxis"

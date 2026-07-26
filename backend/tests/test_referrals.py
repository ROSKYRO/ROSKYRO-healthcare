"""Tests for the referral-rights access control: only certain business
types (clinic, hospital, eye_hospital) may create/choose a referral to a
partner. Everyone else can still list themselves as a partner (see
test_public_marketing.py / partners endpoints), they just can't initiate
one.

Uses the seeded demo accounts (see app/seed.py): Sunrise Family Clinic
(business_type "clinic", subscribed to the "complete" plan bundle -- so it
has the CONNECT pillar active) and Smile Bright Dental (business_type
"dental", subscribed to ["grow", "connect"] -- also has CONNECT active, so
a 403 from this test is really coming from the new business_type gate, not
from a missing-plan 402)."""
import os

DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # business_type: clinic (eligible)
SMILE_DENTAL_EMAIL = "smile.bright.dental@example.com"  # business_type: dental (not eligible)


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _first_partner_id(client, headers):
    resp = client.get("/api/partners", headers=headers)
    assert resp.status_code == 200, resp.text
    partners = resp.json()["partners"]
    assert partners, "expected at least one seeded partner"
    return partners[0]["id"]


def test_eligible_business_type_can_create_referral(client):
    headers = _login(client, SUNRISE_EMAIL)
    partner_id = _first_partner_id(client, headers)

    resp = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id,
        "patientName": "Test Patient (pytest)",
        "serviceRequested": "General Consultation",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["referral"]["referring_org_id"]


def test_ineligible_business_type_cannot_create_referral(client):
    headers = _login(client, SMILE_DENTAL_EMAIL)
    partner_id = _first_partner_id(client, headers)

    resp = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id,
        "patientName": "Test Patient (pytest)",
        "serviceRequested": "General Consultation",
    })
    assert resp.status_code == 403, resp.text
    error = resp.json().get("error", "")
    assert "referral" in error.lower() or "business type" in error.lower()


def test_ineligible_business_type_can_still_register_as_partner(client, unique_suffix):
    """Confirms the access-control change is scoped ONLY to referral
    creation -- becoming a CONNECT partner (register_partner) must remain
    open to every business type."""
    headers = _login(client, SMILE_DENTAL_EMAIL)
    resp = client.get("/api/partners/categories", headers=headers)
    assert resp.status_code == 200, resp.text
    categories = resp.json()["categories"]
    assert categories

    resp = client.post("/api/partners/register", headers=headers, json={
        "categorySlug": categories[0]["slug"],
        "coverageArea": "Pune",
        "turnaroundTime": "Same day",
    })
    assert resp.status_code == 201, resp.text

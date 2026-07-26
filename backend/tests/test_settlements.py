"""Tests for the Referral Bonus model: percentage-based settlement has been
removed entirely -- only flat rupee amounts (or "none"/"custom") are valid."""
DEMO_PASSWORD = "Roskyro@123"
PARTNER_ADMIN_EMAIL = "admin.cityscan.diagnostics@example.com"  # seeded CityScan Diagnostics partner_admin


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_percentage_settlement_type_rejected(client, admin_headers):
    resp = client.post("/api/settlements/rules", headers=admin_headers, json={
        "scope": "platform",
        "settlementType": "percentage",
    })
    assert resp.status_code == 400, resp.text


def test_flat_fee_settlement_type_accepted(client, admin_headers):
    resp = client.post("/api/settlements/rules", headers=admin_headers, json={
        "scope": "platform",
        "settlementType": "flat_fee",
        "flatFeeAmount": 250,
    })
    assert resp.status_code == 201, resp.text
    rule = resp.json()["rule"]
    assert rule["settlement_type"] == "flat_fee"
    assert rule["flat_fee_amount"] == 250


def test_partner_sets_flat_rupee_referral_bonus(client):
    headers = _login(client, PARTNER_ADMIN_EMAIL)
    resp = client.put("/api/settlements/my-rate", headers=headers, json={"flatFeeAmount": 400})
    assert resp.status_code == 200, resp.text
    rate = resp.json()["rate"]
    assert rate["settlement_type"] == "flat_fee"
    assert rate["flat_fee_amount"] == 400
    assert rate.get("percentage_rate") is None

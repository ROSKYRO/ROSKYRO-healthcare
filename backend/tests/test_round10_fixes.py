"""Regression tests for round 10's fix:

plans.py's PATCH /plans/{code} and partner_plans.py's PATCH
/partner-plans/{code} accepted monthlyPrice/yearlyPrice with zero
validation. A non-numeric value saved here doesn't fail at write time --
it sits in the catalog, gets copied into a subscription's
price_at_purchase the next time ANY business (or partner org) subscribes
to that plan, and only THEN crashes with an unhandled ValueError the
first time that org's own GET /plans/mine (my_subscriptions) or GET
/partner-plans/mine (my_partner_subscriptions) does `float(price or 0)`
on it. Same class of gap already fixed for doctors.py/appointments.py/
booking_settings.py in earlier rounds -- an admin-side write with no
numeric check breaking an unrelated, customer/partner-facing read path
later.
"""
import pytest

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _restore_plan_price(client, headers, code, monthly_price, yearly_price):
    """Best-effort restore so this test doesn't leave the shared demo
    catalog's price corrupted for any test that runs after it."""
    client.patch(f"/api/plans/{code}", headers=headers, json={
        "monthlyPrice": monthly_price, "yearlyPrice": yearly_price,
    })


def _restore_partner_plan_price(client, headers, code, monthly_price, yearly_price):
    client.patch(f"/api/partner-plans/{code}", headers=headers, json={
        "monthlyPrice": monthly_price, "yearlyPrice": yearly_price,
    })


# ---------------------------------------------------------------------------
# plans.py -- patch_plan()
# ---------------------------------------------------------------------------

def test_patch_plan_rejects_non_numeric_monthly_price(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/plans/reels", headers=headers, json={"monthlyPrice": "abc"})
    assert resp.status_code == 400, resp.text
    assert "monthly_price" in resp.json()["error"].lower()
    assert "numeric" in resp.json()["error"].lower()


def test_patch_plan_rejects_non_numeric_yearly_price(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/plans/reels", headers=headers, json={"yearlyPrice": "not-a-number"})
    assert resp.status_code == 400, resp.text
    assert "yearly_price" in resp.json()["error"].lower()


def test_patch_plan_accepts_numeric_string_price(client):
    """A numeric-looking value must still work -- only genuinely invalid
    values should be rejected (same lenient-but-safe coercion pattern used
    for doctors.py's consultationFee and booking_settings.py's
    bookingWindowDays fixes in earlier rounds)."""
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/plans/reels", headers=headers, json={"monthlyPrice": "7500"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"]["monthly_price"] == 7500.0
    _restore_plan_price(client, headers, "reels", 6999, 67190)


def test_patch_plan_accepts_real_numbers(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/plans/reels", headers=headers, json={"monthlyPrice": 7250, "yearlyPrice": 69000})
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"]["monthly_price"] == 7250.0
    assert resp.json()["plan"]["yearly_price"] == 69000.0
    _restore_plan_price(client, headers, "reels", 6999, 67190)


def test_patch_plan_bad_price_does_not_corrupt_catalog_or_crash_subscriptions(client):
    """End-to-end: confirm a rejected PATCH never reaches storage, so a
    subsequent GET /plans (public catalog) never sees or serves a broken
    price to anything downstream."""
    headers = _login(client, ADMIN_EMAIL)
    before = client.get("/api/plans")
    assert before.status_code == 200, before.text
    before_price = next(p["monthly_price"] for p in before.json()["plans"] if p["code"] == "reels")

    resp = client.patch("/api/plans/reels", headers=headers, json={"monthlyPrice": "abc"})
    assert resp.status_code == 400, resp.text

    after = client.get("/api/plans")
    assert after.status_code == 200, after.text
    after_price = next(p["monthly_price"] for p in after.json()["plans"] if p["code"] == "reels")
    assert after_price == before_price


# ---------------------------------------------------------------------------
# partner_plans.py -- patch_partner_plan()
# ---------------------------------------------------------------------------

def test_patch_partner_plan_rejects_non_numeric_monthly_price(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"monthlyPrice": "abc"})
    assert resp.status_code == 400, resp.text
    assert "monthly_price" in resp.json()["error"].lower()
    assert "numeric" in resp.json()["error"].lower()


def test_patch_partner_plan_rejects_non_numeric_yearly_price(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"yearlyPrice": "xyz"})
    assert resp.status_code == 400, resp.text
    assert "yearly_price" in resp.json()["error"].lower()


def test_patch_partner_plan_accepts_numeric_string_price(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"monthlyPrice": "7100"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"]["monthly_price"] == 7100.0
    _restore_partner_plan_price(client, headers, "reels", 6999, 67190)


def test_patch_partner_plan_accepts_real_numbers(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"monthlyPrice": 7300, "yearlyPrice": 70000})
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"]["monthly_price"] == 7300.0
    assert resp.json()["plan"]["yearly_price"] == 70000.0
    _restore_partner_plan_price(client, headers, "reels", 6999, 67190)


def test_patch_partner_plan_bad_price_does_not_corrupt_catalog(client):
    headers = _login(client, ADMIN_EMAIL)
    before = client.get("/api/partner-plans")
    assert before.status_code == 200, before.text
    before_price = next(p["monthly_price"] for p in before.json()["plans"] if p["code"] == "reels")

    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"monthlyPrice": "abc"})
    assert resp.status_code == 400, resp.text

    after = client.get("/api/partner-plans")
    assert after.status_code == 200, after.text
    after_price = next(p["monthly_price"] for p in after.json()["plans"] if p["code"] == "reels")
    assert after_price == before_price


def test_patch_plan_still_requires_admin_role(client):
    """Non-admin roles must still be rejected -- this fix must not have
    loosened the existing require_roles("roskyro_admin") gate."""
    resp = client.post("/api/auth/login", json={"identifier": "sunrise.family.clinic@example.com", "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}
    resp = client.patch("/api/plans/reels", headers=headers, json={"monthlyPrice": 7000})
    assert resp.status_code == 403, resp.text

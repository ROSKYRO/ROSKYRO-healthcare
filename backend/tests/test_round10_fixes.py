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

SUPERSEDED (round 15): per explicit product request, partner pricing was
made permanently non-editable on its own -- PATCH /partner-plans/{code}
no longer accepts monthlyPrice/yearlyPrice at all; pricing changes only
ever flow from PATCH /plans/{code} (the business catalog, now the single
source of truth for pricing), which propagates monthly_price/yearly_price
into the matching partner_plans doc automatically. The business-side
(plans.py) numeric-validation tests below are still fully valid and
unchanged. The partner-side price-validation tests below have been
rewritten to assert the new reality (price fields silently ignored on
that endpoint) rather than deleted, so the history of what changed and
why stays in one place -- see test_round15_fixes.py for the full sync
mechanism's own regression tests.
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
    """Restore via the BUSINESS-side endpoint now -- partner-side price
    fields are no longer independently settable (round 15), so the only
    way to move the partner catalog's price is through the sync that
    PATCH /plans/{code} triggers."""
    client.patch(f"/api/plans/{code}", headers=headers, json={
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
#
# SUPERSEDED (round 15): monthlyPrice/yearlyPrice are no longer in
# EDITABLE_PLAN_FIELDS_CAMEL for this endpoint at all -- a body containing
# only price fields now yields the generic "No editable fields provided"
# 400, and the numeric-validation logic these original tests exercised has
# moved entirely to plans.py's patch_plan() (still covered by the
# business-side tests above). These tests now assert THAT new behavior
# instead of the retired one.
# ---------------------------------------------------------------------------

def test_patch_partner_plan_ignores_monthly_price_field(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"monthlyPrice": "abc"})
    assert resp.status_code == 400, resp.text
    assert "no editable fields" in resp.json()["error"].lower()


def test_patch_partner_plan_ignores_yearly_price_field(client):
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"yearlyPrice": "xyz"})
    assert resp.status_code == 400, resp.text
    assert "no editable fields" in resp.json()["error"].lower()


def test_patch_partner_plan_still_allows_copy_fields(client):
    """Non-price fields (name/tagline/etc.) are still editable directly on
    the partner catalog -- only pricing became business-side-only."""
    headers = _login(client, ADMIN_EMAIL)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"tagline": "Reels for partners"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"]["tagline"] == "Reels for partners"


def test_patch_partner_plan_price_fields_do_not_corrupt_catalog(client):
    """Even a mixed body (a valid editable field alongside price fields)
    must not let the price fields sneak through -- price stays whatever it
    was, only the editable field changes."""
    headers = _login(client, ADMIN_EMAIL)
    before = client.get("/api/partner-plans")
    assert before.status_code == 200, before.text
    before_price = next(p["monthly_price"] for p in before.json()["plans"] if p["code"] == "reels")

    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"tagline": "Reels", "monthlyPrice": "abc"})
    assert resp.status_code == 200, resp.text

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

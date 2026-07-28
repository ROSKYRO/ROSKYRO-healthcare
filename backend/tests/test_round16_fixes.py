"""Regression tests for round 16's addition: the super-admin-only "Reset
Demo Data" utility (app/routers/admin_reset.py).

Context: the live Team Dashboard on roskyro.in was showing seeded demo
numbers (9 Active Businesses, 5 Verified Partners, etc.) even though no
real client had been onboarded -- traced to `python -m app.seed` having
been run at least once against the real production database. This adds a
protected, previewable, confirmation-gated endpoint pair so ROSKYRO can
clear all of that demo data in one action and start fresh, without needing
direct database access.

Per explicit user decisions:
- Cleared: every business/partner/referral/subscription/appointment/
  patient/task/notification/etc. record, INCLUDING contact_leads and
  newsletter_subscribers.
- Preserved: the pricing catalog (plans/partner_plans), partner_categories,
  platform_settings (UPI ID, Marketing Fee %), settlement_rules with scope
  "platform"/"category" (only "partner"-scoped rate overrides are cleared),
  and every ROSKYRO internal team account (role in ROSKYRO_ROLES).

test_run_reset_deletes_demo_data_and_preserves_config actually calls the
real, irreversible /run endpoint against the shared session-scoped test
DB every other test in this suite uses -- so it snapshots every touched
collection first and restores everything in a `finally` block, leaving the
DB exactly as it found it regardless of outcome. This is the same
snapshot/restore discipline test_round15_fixes.py already established for
the empty-partner_plans simulation.
"""
import pytest

from app.db import organizations, partners, users
from app.utils.roles import ROSKYRO_ROLES

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"


def _login_admin(client):
    resp = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_preview_and_run_require_admin_role(client, unique_suffix):
    n_body = {
        "orgName": f"Reset Guard Clinic {unique_suffix}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": "Dr Guard",
        "email": f"reset.guard.{unique_suffix}@example.com",
        "phone": f"92{unique_suffix}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    }
    reg = client.post("/api/auth/register", json=n_body)
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}

    resp = client.get("/api/admin/reset-demo-data/preview", headers=headers)
    assert resp.status_code == 403, resp.text

    resp = client.post("/api/admin/reset-demo-data/run", headers=headers, json={"confirm": "DELETE DEMO DATA"})
    assert resp.status_code == 403, resp.text


def test_preview_never_deletes_anything(client):
    """Calling /preview repeatedly must return the same counts -- it's
    read-only."""
    headers = _login_admin(client)
    first = client.get("/api/admin/reset-demo-data/preview", headers=headers)
    assert first.status_code == 200, first.text
    second = client.get("/api/admin/reset-demo-data/preview", headers=headers)
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert first.json()["total"] > 0  # sanity: seeded demo data really is present
    assert "preserved" in first.json()


def test_run_rejects_missing_or_wrong_confirm_phrase(client):
    """None of these come close enough to "DELETE DEMO DATA" to pass --
    the exact-match confirmation (a trimmed but otherwise case-sensitive
    match) is separately tested as a positive case in
    test_run_reset_deletes_demo_data_and_preserves_config, which sends a
    trailing-space variant and expects it to succeed."""
    headers = _login_admin(client)
    before = client.get("/api/admin/reset-demo-data/preview", headers=headers).json()["total"]

    for bad_body in ({}, {"confirm": ""}, {"confirm": "delete demo data"}, {"confirm": "yes"}, {"confirm": "DELETE DEMO DAT"}):
        resp = client.post("/api/admin/reset-demo-data/run", headers=headers, json=bad_body)
        assert resp.status_code == 400, f"body={bad_body} resp={resp.text}"

    # Confirm nothing was deleted by any of the rejected attempts.
    after = client.get("/api/admin/reset-demo-data/preview", headers=headers).json()["total"]
    assert after == before


@pytest.mark.asyncio
async def test_run_reset_deletes_demo_data_and_preserves_config(client):
    """The real, irreversible happy path. Snapshots every collection this
    endpoint touches and restores all of them in `finally`, so this test
    leaves the shared demo DB exactly as it found it for every test that
    runs after it."""
    from app.routers.admin_reset import _TARGETS

    snapshots = {}
    for _label, collection, _filt in _TARGETS:
        snapshots[collection.name] = await collection.find({}).to_list(None)

    try:
        headers = _login_admin(client)

        # seed.py never populates platform_settings (a real deployment
        # configures the UPI ID by hand via Pricing & Payments) -- set one
        # here so this test can actually verify it SURVIVES the reset,
        # matching the real production scenario where an admin has already
        # configured it.
        upi_resp = client.patch("/api/settings/payment", headers=headers, json={"upiId": "roskyro@okhdfcbank"})
        assert upi_resp.status_code == 200, upi_resp.text

        preview_before = client.get("/api/admin/reset-demo-data/preview", headers=headers).json()
        assert preview_before["total"] > 0

        resp = client.post("/api/admin/reset-demo-data/run", headers=headers, json={"confirm": "DELETE DEMO DATA "})
        assert resp.status_code == 200, resp.text
        assert resp.json()["totalDeleted"] == preview_before["total"]

        # Demo operational data is actually gone.
        assert await organizations.count_documents({}) == 0
        assert await partners.count_documents({}) == 0
        remaining_users = await users.find({}).to_list(None)
        assert len(remaining_users) > 0  # the ROSKYRO team itself must survive
        assert all(u["role"] in ROSKYRO_ROLES for u in remaining_users)

        # Preserved config/catalog untouched.
        plans_resp = client.get("/api/plans")
        assert plans_resp.status_code == 200
        assert {p["code"] for p in plans_resp.json()["plans"]} == {"grow", "manage", "connect", "complete", "reels"}

        partner_plans_resp = client.get("/api/partner-plans")
        assert partner_plans_resp.status_code == 200
        assert {p["code"] for p in partner_plans_resp.json()["plans"]} == {"grow", "manage", "connect", "complete", "reels"}

        payment_resp = client.get("/api/settings/payment")
        assert payment_resp.status_code == 200
        assert payment_resp.json()["upi_id"]  # still configured, not wiped to null

        # A second preview now shows just 1 -- the reset's own audit-log
        # entry (audit_logs is itself cleared, then this one entry is
        # written recording who ran the reset and what was removed).
        preview_after = client.get("/api/admin/reset-demo-data/preview", headers=headers).json()
        assert preview_after["total"] == 1
        assert preview_after["items"] == [i for i in preview_after["items"] if i["count"] == 0 or i["label"] == "Audit log entries"]

        # The ROSKYRO admin's own account is untouched -- can still log in.
        relogin = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": DEMO_PASSWORD})
        assert relogin.status_code == 200, relogin.text
    finally:
        for _label, collection, _filt in _TARGETS:
            await collection.delete_many({})
            docs = snapshots[collection.name]
            if docs:
                await collection.insert_many(docs)


@pytest.mark.asyncio
async def test_run_reset_preserves_platform_and_category_settlement_rates(client):
    """Only "partner"-scoped rate overrides should be cleared -- the
    already-configured platform default and category default rates must
    survive a reset."""
    from app.db import settlement_rules
    from app.routers.admin_reset import _TARGETS

    snapshots = {}
    for _label, collection, _filt in _TARGETS:
        snapshots[collection.name] = await collection.find({}).to_list(None)

    try:
        platform_before = await settlement_rules.count_documents({"scope": "platform"})
        category_before = await settlement_rules.count_documents({"scope": "category"})
        partner_before = await settlement_rules.count_documents({"scope": "partner"})
        assert platform_before > 0 and category_before > 0 and partner_before > 0  # sanity

        headers = _login_admin(client)
        resp = client.post("/api/admin/reset-demo-data/run", headers=headers, json={"confirm": "DELETE DEMO DATA"})
        assert resp.status_code == 200, resp.text

        assert await settlement_rules.count_documents({"scope": "platform"}) == platform_before
        assert await settlement_rules.count_documents({"scope": "category"}) == category_before
        assert await settlement_rules.count_documents({"scope": "partner"}) == 0
    finally:
        for _label, collection, _filt in _TARGETS:
            await collection.delete_many({})
            docs = snapshots[collection.name]
            if docs:
                await collection.insert_many(docs)

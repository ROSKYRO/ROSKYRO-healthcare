"""Regression tests for round 15's changes, made per two explicit product
decisions from the user (not a routine bug-check round):

1. The "buy 2 pillars, get the 3rd free" bundle-bonus mechanic is retired
   entirely (not just its marketing text) -- business: MANAGE + GROW active
   used to auto-grant CONNECT free; partner: GROW + CONNECT active used to
   auto-grant MANAGE free. Both grant paths (apply_bundle_bonus) and both
   auto-revoke paths (revoke_bundle_bonus_if_broken) have been deleted from
   app/utils/bundle_bonus.py, and routers/plans.py + routers/partner_plans.py
   no longer call them or return bonusGranted/bonusRevoked in any response.
   Per this engagement's conservative-removal principle: this only stops
   NEW bonus grants going forward -- any org that was already granted a free
   bonus subscription before this change keeps it (silently clawing back an
   already-delivered free service would be a separate, real billing decision,
   not made here).

   The two UNRELATED functions that happened to live in the same file --
   find_active_bundle_covering_pillar (the "ROSKYRO Complete" bundle-plan
   double-billing guard) and cascade_cancel_dependent_addons (the "reels"
   add-on dependency cleanup) -- are untouched and still fully active; this
   file does not re-test them (see test_business_partner_pricing.py's
   existing test_reels_addon_requires_grow_and_cascades_on_cancel).

2. Partner-audience pricing is now PERMANENTLY synced to the business
   catalog: PATCH /plans/{code} (business side) propagates monthly_price/
   yearly_price into the matching partner_plans doc, and PATCH
   /partner-plans/{code} no longer accepts monthlyPrice/yearlyPrice at all
   -- closing the exact gap (separate admin-editable prices per audience)
   that let the two pricing tabs show different numbers for the same
   service on the live site.

3. HARDENED after being spotted live on roskyro.in: the "For Partners"
   pricing tab was rendering a completely blank list in production (no
   cards at all between the audience toggle and the Enterprise section),
   and POST /partner-plans/subscribe 404'd as "Unknown plan." for a
   perfectly valid code. Root cause: every read in routers/partner_plans.py
   queried the partner_plans collection directly, and on the real
   deployment that collection was never separately populated for every
   code (unlike the mock/demo DB, where seed.py always deep-copies the
   business catalog into it). Fixed by routing every catalog read in that
   file through _effective_partner_plans_map(), which uses the business
   `plans` collection as the guaranteed-populated base and only lets an
   existing partner_plans doc override copy fields (never price). The
   tests below simulate the production condition directly (temporarily
   emptying partner_plans) to prove the fix, then restore the collection
   so later tests in this run aren't affected.

See test_business_partner_pricing.py for the companion tests covering the
same two changes end-to-end via the subscribe/cancel and catalog-GET flows;
this file focuses on the sync mechanism and dead-code removal specifically.
"""
import itertools

import pytest

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"
PUNELIFE_PARTNER_EMAIL = "admin.punelife.imaging.centre@example.com"  # partner_admin, seeded with only GROW active

_reg_counter = itertools.count(1)


def _login_admin(client):
    resp = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _register_business(client, unique_suffix):
    n = next(_reg_counter)
    resp = client.post("/api/auth/register", json={
        "orgName": f"Round15 Test Clinic {unique_suffix}{n}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": "Dr. Round15 Test",
        "email": f"round15.test.{unique_suffix}{n}@example.com",
        "phone": f"96{unique_suffix}{n}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def _headers(reg):
    return {"Authorization": f"Bearer {reg['token']}"}


# ---------------------------------------------------------------------------
# bundle_bonus.py -- dead code actually removed, not just unreachable
# ---------------------------------------------------------------------------

def test_apply_and_revoke_bundle_bonus_functions_no_longer_exist():
    """Confirms the retired functions were actually deleted from the module
    (not just made unreachable), so no future code can accidentally start
    calling them again."""
    import app.utils.bundle_bonus as bundle_bonus_module

    assert not hasattr(bundle_bonus_module, "apply_bundle_bonus")
    assert not hasattr(bundle_bonus_module, "revoke_bundle_bonus_if_broken")

    # The two unrelated features must still be present and untouched.
    assert hasattr(bundle_bonus_module, "find_active_bundle_covering_pillar")
    assert hasattr(bundle_bonus_module, "cascade_cancel_dependent_addons")
    assert hasattr(bundle_bonus_module, "_pillar_still_covered")


# ---------------------------------------------------------------------------
# plans.py / partner_plans.py -- bonus mechanic actually retired end-to-end
# ---------------------------------------------------------------------------

def test_business_subscribe_and_cancel_responses_have_no_bonus_keys(client, unique_suffix):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)

    sub_resp = client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    assert sub_resp.status_code == 201, sub_resp.text
    assert "bonusGranted" not in sub_resp.json()
    assert set(sub_resp.json().keys()) == {"subscription"}

    cancel_resp = client.post("/api/plans/cancel", json={"planCode": "manage"}, headers=headers)
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert "bonusRevoked" not in cancel_resp.json()
    assert set(cancel_resp.json().keys()) == {"subscription", "addonsCancelled"}


def test_patch_partner_plan_response_has_no_bonus_keys(client):
    """The end-to-end subscribe/cancel bonus-removal check for the partner
    audience already lives in test_business_partner_pricing.py's
    test_partner_manage_and_grow_no_longer_unlock_connect_free. This locks
    down that patch_partner_plan's own response never grew a bonus-shaped
    key either, since it shares partner_plans.py with subscribe/cancel."""
    headers = _login_admin(client)
    resp = client.patch("/api/partner-plans/reels", headers=headers, json={"tagline": "Reels"})
    assert resp.status_code == 200, resp.text
    assert "bonusGranted" not in resp.json() and "bonusRevoked" not in resp.json()


# ---------------------------------------------------------------------------
# Permanent price sync -- plans.py -> partner_plans.py
# ---------------------------------------------------------------------------

def test_patching_business_price_propagates_to_partner_catalog(client):
    headers = _login_admin(client)

    before = client.get("/api/partner-plans").json()["plans"]
    before_plan = next(p for p in before if p["code"] == "grow")
    before_monthly, before_yearly = before_plan["monthly_price"], before_plan["yearly_price"]

    resp = client.patch("/api/plans/grow", headers=headers, json={"monthlyPrice": 5555, "yearlyPrice": 55550})
    assert resp.status_code == 200, resp.text
    assert resp.json()["plan"]["monthly_price"] == 5555.0

    partner_plan = next(p for p in client.get("/api/partner-plans").json()["plans"] if p["code"] == "grow")
    assert partner_plan["monthly_price"] == 5555.0
    assert partner_plan["yearly_price"] == 55550.0

    client.patch("/api/plans/grow", headers=headers, json={"monthlyPrice": before_monthly, "yearlyPrice": before_yearly})


def test_patching_business_non_price_field_does_not_touch_partner_price(client):
    """The sync must be scoped to price fields only -- editing a business
    plan's copy (name/tagline/etc.) must not overwrite anything on the
    partner side (they're allowed to have different copy, just not
    different prices)."""
    headers = _login_admin(client)

    partner_before = next(p for p in client.get("/api/partner-plans").json()["plans"] if p["code"] == "manage")

    resp = client.patch("/api/plans/manage", headers=headers, json={"tagline": "Business-only tagline change"})
    assert resp.status_code == 200, resp.text

    partner_after = next(p for p in client.get("/api/partner-plans").json()["plans"] if p["code"] == "manage")
    assert partner_after["monthly_price"] == partner_before["monthly_price"]
    assert partner_after["yearly_price"] == partner_before["yearly_price"]


def test_patch_partner_plan_rejects_price_only_body(client):
    headers = _login_admin(client)
    resp = client.patch("/api/partner-plans/complete", headers=headers, json={
        "monthlyPrice": 11111, "yearlyPrice": 111110,
    })
    assert resp.status_code == 400, resp.text
    assert "no editable fields" in resp.json()["error"].lower()


def test_patch_plan_still_requires_admin_role_after_sync_change(client, unique_suffix):
    """The sync addition must not have loosened the existing
    require_roles("roskyro_admin") gate on either endpoint."""
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)

    resp = client.patch("/api/plans/grow", headers=headers, json={"monthlyPrice": 1})
    assert resp.status_code == 403, resp.text

    resp = client.patch("/api/partner-plans/grow", headers=headers, json={"tagline": "hacked"})
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# HARDENING -- partner_plans collection empty/unpopulated (the actual bug
# spotted live on roskyro.in). These simulate that production condition
# directly against the shared session DB, and restore it afterward in a
# try/finally so no later test in this run is affected.
# ---------------------------------------------------------------------------

async def _snapshot_and_empty_partner_plans():
    from app.db import partner_plans
    docs = await partner_plans.find({}).to_list(None)
    await partner_plans.delete_many({})
    return docs


async def _restore_partner_plans(docs):
    """Clears whatever the test itself inserted (e.g. an upsert from
    patch_partner_plan) before restoring the original snapshot -- otherwise
    a doc the test created for a code that was already in the snapshot
    collides on insert_many with a duplicate _id."""
    from app.db import partner_plans
    await partner_plans.delete_many({})
    if docs:
        await partner_plans.insert_many(docs)


@pytest.mark.asyncio
async def test_partner_catalog_list_survives_empty_partner_plans_collection(client):
    """The exact bug from the screenshot: an empty partner_plans collection
    must NOT produce a blank "For Partners" pricing list -- it must fall
    back to the (always-populated) business catalog, code-for-code."""
    docs = await _snapshot_and_empty_partner_plans()
    try:
        resp = client.get("/api/partner-plans")
        assert resp.status_code == 200, resp.text
        plans = resp.json()["plans"]
        codes = {p["code"] for p in plans}
        assert codes == {"grow", "manage", "connect", "complete", "reels"}

        business_by_code = {p["code"]: p for p in client.get("/api/plans").json()["plans"]}
        for p in plans:
            assert p["monthly_price"] == business_by_code[p["code"]]["monthly_price"]
            assert p["yearly_price"] == business_by_code[p["code"]]["yearly_price"]
    finally:
        await _restore_partner_plans(docs)


@pytest.mark.asyncio
async def test_partner_subscribe_survives_empty_partner_plans_collection(client):
    """The other half of the live bug: subscribing to a partner plan must
    not 404 as "Unknown plan." just because partner_plans has no row for
    it -- the business catalog is the real source of truth now."""
    docs = await _snapshot_and_empty_partner_plans()
    try:
        partner_login = client.post("/api/auth/login", json={
            "identifier": PUNELIFE_PARTNER_EMAIL, "password": DEMO_PASSWORD,
        })
        assert partner_login.status_code == 200, partner_login.text
        headers = {"Authorization": f"Bearer {partner_login.json()['token']}"}

        resp = client.post("/api/partner-plans/subscribe", json={"planCode": "reels"}, headers=headers)
        assert resp.status_code in (201, 409), resp.text  # 409 if reels was already active from an earlier test run
        if resp.status_code == 201:
            client.post("/api/partner-plans/cancel", json={"planCode": "reels"}, headers=headers)  # clean up
    finally:
        await _restore_partner_plans(docs)


@pytest.mark.asyncio
async def test_patch_partner_plan_upserts_when_no_row_exists_yet(client):
    """An admin editing partner-side copy for a code that has no
    partner_plans row at all yet must not 404 -- it should create that row
    (upsert) rather than requiring one to already exist."""
    docs = await _snapshot_and_empty_partner_plans()
    try:
        headers = _login_admin(client)
        resp = client.patch("/api/partner-plans/manage", headers=headers, json={"tagline": "Partner-only tagline"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["plan"]["tagline"] == "Partner-only tagline"
        # Pricing must still come from the business catalog even on a
        # freshly-upserted row.
        business_manage = next(p for p in client.get("/api/plans").json()["plans"] if p["code"] == "manage")
        assert resp.json()["plan"]["monthly_price"] == business_manage["monthly_price"]
    finally:
        await _restore_partner_plans(docs)

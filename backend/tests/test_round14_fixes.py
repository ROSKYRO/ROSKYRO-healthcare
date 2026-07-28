"""Regression tests for round 14's fixes:

1. main.py had no safeguard at all if a real (USE_MOCK_DB=false) deployment
   never overrode config.py's hardcoded JWT_SECRET / ADMIN_PASSWORD
   defaults -- admin_bootstrap.py's sync_super_admin() runs on every boot
   and actively resets the super-admin password back to whatever
   ADMIN_PASSWORD currently resolves to, so a deployment that forgot to
   set these in its environment would silently run forever with a
   publicly-known admin password and a JWT signing secret sitting in
   source code. Fixed with a loud startup warning (never a hard failure --
   a misconfigured secret shouldn't crash-loop a deployment) whenever a
   real DB is in use and either value still equals its literal default.

2. partners.py's list_partners (GET /api/partners, the customer-facing
   Partner Directory) did an unbounded `.to_list(None)` -- with no
   category/verifiedOnly/availableOnly filter (the default view), this
   pulled every partner on the entire platform into memory before
   enrichment, sort, and a final Python-side slice to 200. Fixed with a
   generous-but-bounded `.to_list(2000)`, matching the same
   fetch-everything-then-slice-in-Python fix already applied elsewhere in
   this codebase (tasks.py's list_tasks).

3. patient_followups had no index covering followups.py's list endpoint's
   actual query shape (org_id [+ status] filter, sorted by due_date) --
   only an (org_id, patient_name) index existed, added for a different
   endpoint (patients.py's per-patient lookup). Fixed by adding
   (org_id, status, due_date) to db_indexes.py's _INDEX_PLAN.
"""
import logging

import pytest

DEMO_PASSWORD = "Roskyro@123"


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# ---------------------------------------------------------------------------
# main.py -- insecure production defaults warning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_warns_on_default_secrets_with_real_db(monkeypatch, caplog):
    import app.main as main_module

    monkeypatch.setattr(main_module, "USE_MOCK_DB", False)
    monkeypatch.setattr(main_module, "JWT_SECRET", "change_this_secret_in_production")
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", "Roskyro@123")

    with caplog.at_level(logging.WARNING, logger="roskyro"):
        await main_module.warn_on_insecure_production_defaults()

    messages = "\n".join(r.message for r in caplog.records)
    assert "JWT_SECRET" in messages
    assert "ADMIN_PASSWORD" in messages


@pytest.mark.asyncio
async def test_no_warning_when_using_mock_db(monkeypatch, caplog):
    """The mock/dev/test setup is EXPECTED to use the defaults -- this
    must never fire for USE_MOCK_DB=true, regardless of the secret values."""
    import app.main as main_module

    monkeypatch.setattr(main_module, "USE_MOCK_DB", True)
    monkeypatch.setattr(main_module, "JWT_SECRET", "change_this_secret_in_production")
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", "Roskyro@123")

    with caplog.at_level(logging.WARNING, logger="roskyro"):
        await main_module.warn_on_insecure_production_defaults()

    assert caplog.records == []


@pytest.mark.asyncio
async def test_no_warning_when_secrets_overridden(monkeypatch, caplog):
    import app.main as main_module

    monkeypatch.setattr(main_module, "USE_MOCK_DB", False)
    monkeypatch.setattr(main_module, "JWT_SECRET", "a-real-random-production-secret")
    monkeypatch.setattr(main_module, "ADMIN_PASSWORD", "SomeRealProdPassword123!")

    with caplog.at_level(logging.WARNING, logger="roskyro"):
        await main_module.warn_on_insecure_production_defaults()

    assert caplog.records == []


# ---------------------------------------------------------------------------
# partners.py -- bounded directory fetch
# ---------------------------------------------------------------------------

def test_partner_directory_still_works_with_bounded_fetch(client):
    """Functional regression check for the .to_list(None) -> .to_list(2000)
    change -- confirms the endpoint still returns the seeded partners
    correctly (the cap itself can't be exercised at real scale in a unit
    test, but the change must not have broken normal operation)."""
    resp = client.post("/api/auth/login", json={"identifier": "sunrise.family.clinic@example.com", "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['token']}"}

    listing = client.get("/api/partners", headers=headers)
    assert listing.status_code == 200, listing.text
    assert isinstance(listing.json()["partners"], list)
    assert len(listing.json()["partners"]) > 0


# ---------------------------------------------------------------------------
# db_indexes.py -- patient_followups (org_id, status, due_date) index
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_patient_followups_due_date_index_created_without_collision():
    """Direct DB-level check (per this engagement's established index-
    collision gotcha -- see db_indexes.py's own warning comment) that the
    new (org_id, status, due_date) compound index actually exists after
    ensure_indexes() runs, rather than silently failing to create (e.g. an
    unrelated same-key-pattern index already claiming that index name)."""
    from app.db_indexes import ensure_indexes
    from app.db import patient_followups

    await ensure_indexes()
    index_info = await patient_followups.index_information()
    key_patterns = [tuple(spec["key"]) for spec in index_info.values()]
    assert (("org_id", 1), ("status", 1), ("due_date", 1)) in key_patterns, (
        f"expected an (org_id, status, due_date) index on patient_followups, found: {key_patterns}"
    )

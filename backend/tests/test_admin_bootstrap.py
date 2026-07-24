"""Unit-level tests for app/admin_bootstrap.py's sync_super_admin(), run
directly against the DB layer (not through HTTP) so they can freely
create/inspect user documents by role without needing an authenticated
caller. See ADMIN_EMAIL / ADMIN_PASSWORD in RAILWAY-DEPLOY-GUIDE.md for
the feature this covers."""
import pytest

from app.db import users
from app.auth import verify_password


@pytest.mark.asyncio
async def test_sync_is_idempotent_and_does_not_duplicate(client):
    """`client` fixture guarantees app startup (and therefore the first
    sync_super_admin() call) has already run once."""
    from app.admin_bootstrap import sync_super_admin

    before = await users.count_documents({"role": "roskyro_admin"})
    await sync_super_admin()
    await sync_super_admin()
    after = await users.count_documents({"role": "roskyro_admin"})
    assert after == before == 1


@pytest.mark.asyncio
async def test_sync_updates_password_when_env_changes(client, monkeypatch):
    import app.admin_bootstrap as admin_bootstrap

    monkeypatch.setattr(admin_bootstrap, "ADMIN_PASSWORD", "RotatedPassword@9")
    await admin_bootstrap.sync_super_admin()

    admin = await users.find_one({"role": "roskyro_admin"})
    assert verify_password("RotatedPassword@9", admin["password_hash"])

    # Restore, so later tests (and the `admin_headers` fixture) still see
    # the original default password.
    monkeypatch.undo()
    await admin_bootstrap.sync_super_admin()
    admin_again = await users.find_one({"role": "roskyro_admin"})
    assert verify_password("Roskyro@123", admin_again["password_hash"])

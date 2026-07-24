"""Keeps the ROSKYRO super-admin login in sync with the ADMIN_EMAIL /
ADMIN_PASSWORD environment variables -- the same pattern the original app
used (ADMIN_USERNAME / ADMIN_PASSWORD, reconciled on every boot in
server.py's lifespan()), so production credentials live in Railway's
Variables tab instead of in seed data or source code.

`sync_super_admin()` is called from two places:
  1. main.py's startup event -- runs on every boot, real DB or mock, so
     the super-admin account exists (and matches the env vars) even on a
     brand new deployment that has never had `python -m app.seed` run
     against it.
  2. the end of app/seed.py's `run()` -- so re-running the demo seed
     never quietly resets a production admin password back to the seed
     default.

Idempotent: no matching account -> creates one; account exists but
email/password no longer match the env vars -> updates just those
fields; already matches -> no-op (no unnecessary writes on every boot).
"""
from app.config import ADMIN_EMAIL, ADMIN_PASSWORD
from app.db import users
from app.auth import hash_password, verify_password
from app.utils.ids import new_id, now


async def sync_super_admin():
    existing = await users.find_one({"role": "roskyro_admin", "org_id": None})

    if existing is None:
        await users.insert_one({
            "_id": new_id(), "org_id": None, "name": "ROSKYRO Admin",
            "email": ADMIN_EMAIL, "password_hash": hash_password(ADMIN_PASSWORD),
            "phone": "+91-9800000000", "role": "roskyro_admin", "status": "active",
            "avatar_url": None, "last_login_at": None,
            "created_at": now(), "updated_at": now(),
        })
        return

    updates = {}
    if existing.get("email") != ADMIN_EMAIL:
        updates["email"] = ADMIN_EMAIL
    if not existing.get("password_hash") or not verify_password(ADMIN_PASSWORD, existing["password_hash"]):
        updates["password_hash"] = hash_password(ADMIN_PASSWORD)
    if updates:
        updates["updated_at"] = now()
        await users.update_one({"_id": existing["_id"]}, {"$set": updates})

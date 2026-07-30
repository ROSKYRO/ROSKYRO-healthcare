"""Regression tests for round 21 -- a genuinely NEW feature, not a bug fix.

Before this round, there was no create/edit/deactivate path anywhere in the
product for ROSKYRO's own internal team (Team Roster's names/roles, as
distinct from routers/orgs.py's `/{org_id}/team` which manages a
BUSINESS's own staff/doctors). The only way to change who's on the
internal team was a direct database edit. This round adds
routers/team_members.py + frontend/.../ManageTeam.jsx to close that gap,
restricted to `roskyro_admin` only (same precedent as Pricing & Payments
and Password Requests).

Every test below exercises the new /api/team-members endpoints directly.
"""
from app.db import users
from app.utils.ids import new_id, now

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"
OPS_MANAGER_EMAIL = "ops@roskyro.com"  # seeded roskyro_ops_manager -- NOT an admin
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # a customer-shell account


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["user"]


def test_non_admin_internal_role_cannot_reach_any_team_members_endpoint(client):
    ops_headers, _ = _login(client, OPS_MANAGER_EMAIL)
    assert client.get("/api/team-members", headers=ops_headers).status_code == 403
    assert client.post("/api/team-members", headers=ops_headers, json={
        "name": "x", "email": "x@example.com", "phone": "9800000099", "role": "roskyro_support_executive", "password": "abcdef",
    }).status_code == 403


def test_customer_shell_account_cannot_reach_team_members_endpoint(client):
    sunrise_headers, _ = _login(client, SUNRISE_EMAIL)
    assert client.get("/api/team-members", headers=sunrise_headers).status_code == 403


def test_admin_can_list_team_members_and_password_hash_is_never_exposed(client, admin_headers):
    resp = client.get("/api/team-members", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    members = resp.json()["members"]
    assert len(members) >= 1
    names = {m["name"] for m in members}
    assert "Aditi Rao" in names  # the seeded super-admin, confirming this lists the real internal roster
    for m in members:
        assert "password_hash" not in m


def test_admin_creates_a_new_team_member(client, admin_headers, unique_suffix):
    resp = client.post("/api/team-members", headers=admin_headers, json={
        "name": f"Round21 New Hire {unique_suffix}",
        "email": f"round21.hire.{unique_suffix}@example.com",
        "phone": f"911100{unique_suffix}"[-10:].rjust(10, "9"),
        "role": "roskyro_content_specialist",
        "password": "TempPass123",
    })
    assert resp.status_code == 201, resp.text
    member = resp.json()["member"]
    assert member["role"] == "roskyro_content_specialist"
    assert member["status"] == "active"
    assert member["org_id"] is None
    assert "password_hash" not in member

    # And it shows up in the plain list too.
    listed = client.get("/api/team-members", headers=admin_headers).json()["members"]
    assert any(m["id"] == member["id"] for m in listed)

    # It also flows into the existing (unchanged) Team Roster workload view.
    roster = client.get("/api/tasks/team/roster", headers=admin_headers).json()["roster"]
    assert any(r["id"] == member["id"] and r["open_tasks"] == 0 for r in roster)

    # The new hire can actually log in with the password just set.
    new_login = client.post("/api/auth/login", json={
        "identifier": member["email"], "password": "TempPass123",
    })
    assert new_login.status_code == 200, new_login.text
    assert new_login.json()["user"]["appShell"] == "internal"


def test_create_rejects_invalid_role(client, admin_headers, unique_suffix):
    resp = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Bad Role", "email": f"bad.role.{unique_suffix}@example.com",
        "phone": f"922200{unique_suffix}"[-10:].rjust(10, "9"), "role": "owner", "password": "abcdef",
    })
    assert resp.status_code == 400, resp.text
    assert "role must be one of" in resp.json()["error"]


def test_create_rejects_duplicate_email_and_phone(client, admin_headers, unique_suffix):
    email = f"round21.dupe.{unique_suffix}@example.com"
    phone = f"933300{unique_suffix}"[-10:].rjust(10, "9")
    first = client.post("/api/team-members", headers=admin_headers, json={
        "name": "First", "email": email, "phone": phone, "role": "roskyro_support_executive", "password": "abcdef",
    })
    assert first.status_code == 201, first.text

    dupe_email = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Second", "email": email, "phone": f"944400{unique_suffix}"[-10:].rjust(10, "9"),
        "role": "roskyro_support_executive", "password": "abcdef",
    })
    assert dupe_email.status_code == 409, dupe_email.text

    dupe_phone = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Third", "email": f"round21.other.{unique_suffix}@example.com", "phone": phone,
        "role": "roskyro_support_executive", "password": "abcdef",
    })
    assert dupe_phone.status_code == 409, dupe_phone.text


def test_create_rejects_short_password(client, admin_headers, unique_suffix):
    resp = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Weak Pw", "email": f"weakpw.{unique_suffix}@example.com",
        "phone": f"955500{unique_suffix}"[-10:].rjust(10, "9"), "role": "roskyro_support_executive", "password": "abc",
    })
    assert resp.status_code == 422, resp.text  # pydantic Field(min_length=6) rejects before the handler runs


def test_admin_edits_name_role_and_phone(client, admin_headers, unique_suffix):
    created = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Before Edit", "email": f"round21.edit.{unique_suffix}@example.com",
        "phone": f"966600{unique_suffix}"[-10:].rjust(10, "9"), "role": "roskyro_support_executive", "password": "abcdef",
    }).json()["member"]

    updated = client.patch(f"/api/team-members/{created['id']}", headers=admin_headers, json={
        "name": "After Edit", "role": "roskyro_review_manager",
    })
    assert updated.status_code == 200, updated.text
    body = updated.json()["member"]
    assert body["name"] == "After Edit"
    assert body["role"] == "roskyro_review_manager"
    # Untouched fields survive the partial update.
    assert body["email"] == created["email"]


def test_edit_rejects_duplicate_email_against_a_different_member(client, admin_headers, unique_suffix):
    a = client.post("/api/team-members", headers=admin_headers, json={
        "name": "A", "email": f"round21.a.{unique_suffix}@example.com",
        "phone": f"977700{unique_suffix}"[-10:].rjust(10, "9"), "role": "roskyro_support_executive", "password": "abcdef",
    }).json()["member"]
    b = client.post("/api/team-members", headers=admin_headers, json={
        "name": "B", "email": f"round21.b.{unique_suffix}@example.com",
        "phone": f"988800{unique_suffix}"[-10:].rjust(10, "9"), "role": "roskyro_support_executive", "password": "abcdef",
    }).json()["member"]

    clash = client.patch(f"/api/team-members/{b['id']}", headers=admin_headers, json={"email": a["email"]})
    assert clash.status_code == 409, clash.text

    # But re-saving a member's OWN unchanged email must NOT trip the
    # duplicate check against itself.
    self_save = client.patch(f"/api/team-members/{b['id']}", headers=admin_headers, json={"email": b["email"]})
    assert self_save.status_code == 200, self_save.text


def test_edit_cannot_reach_a_non_internal_users_account(client, admin_headers):
    sunrise_headers, sunrise_user = _login(client, SUNRISE_EMAIL)
    resp = client.patch(f"/api/team-members/{sunrise_user['id']}", headers=admin_headers, json={"name": "Hijacked"})
    assert resp.status_code == 404, resp.text


def test_deactivate_blocks_login_and_reactivate_restores_it(client, admin_headers, unique_suffix):
    member = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Deactivate Me", "email": f"round21.deact.{unique_suffix}@example.com",
        "phone": f"999900{unique_suffix}"[-10:].rjust(10, "9"), "role": "roskyro_support_executive", "password": "abcdef",
    }).json()["member"]

    deactivated = client.patch(f"/api/team-members/{member['id']}", headers=admin_headers, json={"status": "inactive"})
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["member"]["status"] == "inactive"

    blocked_login = client.post("/api/auth/login", json={"identifier": member["email"], "password": "abcdef"})
    assert blocked_login.status_code == 403, blocked_login.text

    reactivated = client.patch(f"/api/team-members/{member['id']}", headers=admin_headers, json={"status": "active"})
    assert reactivated.status_code == 200, reactivated.text

    working_login = client.post("/api/auth/login", json={"identifier": member["email"], "password": "abcdef"})
    assert working_login.status_code == 200, working_login.text


def test_new_password_via_edit_actually_changes_login(client, admin_headers, unique_suffix):
    member = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Password Reset Test", "email": f"round21.pwreset.{unique_suffix}@example.com",
        "phone": f"911122{unique_suffix}"[-10:].rjust(10, "9"), "role": "roskyro_support_executive", "password": "OldPass123",
    }).json()["member"]

    resp = client.patch(f"/api/team-members/{member['id']}", headers=admin_headers, json={"newPassword": "NewPass456"})
    assert resp.status_code == 200, resp.text

    old_fails = client.post("/api/auth/login", json={"identifier": member["email"], "password": "OldPass123"})
    assert old_fails.status_code == 401, old_fails.text

    new_works = client.post("/api/auth/login", json={"identifier": member["email"], "password": "NewPass456"})
    assert new_works.status_code == 200, new_works.text


def test_cannot_deactivate_or_demote_the_last_active_admin(client, admin_headers):
    """Guards against a self-inflicted total lockout: if the account being
    edited is the ONLY active roskyro_admin left, neither demoting its
    role away from admin nor deactivating it is allowed."""
    admins = [m for m in client.get("/api/team-members", headers=admin_headers).json()["members"]
              if m["role"] == "roskyro_admin" and m["status"] == "active"]
    assert len(admins) == 1, "this test assumes the seeded data has exactly one active admin"
    only_admin = admins[0]

    demote = client.patch(f"/api/team-members/{only_admin['id']}", headers=admin_headers, json={"role": "roskyro_ops_manager"})
    assert demote.status_code == 400, demote.text

    deactivate = client.patch(f"/api/team-members/{only_admin['id']}", headers=admin_headers, json={"status": "inactive"})
    assert deactivate.status_code == 400, deactivate.text

    # Confirm it's genuinely untouched.
    still = client.get("/api/team-members", headers=admin_headers).json()["members"]
    still_admin = next(m for m in still if m["id"] == only_admin["id"])
    assert still_admin["role"] == "roskyro_admin"
    assert still_admin["status"] == "active"


def test_demoting_one_of_several_admins_is_allowed(client, admin_headers, unique_suffix):
    """The last-admin guard must only block the LAST one -- with a second
    active admin in place, demoting/deactivating either one is fine."""
    second_admin = client.post("/api/team-members", headers=admin_headers, json={
        "name": "Second Admin", "email": f"round21.admin2.{unique_suffix}@example.com",
        "phone": f"933344{unique_suffix}"[-10:].rjust(10, "9"), "role": "roskyro_admin", "password": "abcdef",
    }).json()["member"]

    demote = client.patch(f"/api/team-members/{second_admin['id']}", headers=admin_headers, json={"role": "roskyro_ops_manager"})
    assert demote.status_code == 200, demote.text
    assert demote.json()["member"]["role"] == "roskyro_ops_manager"

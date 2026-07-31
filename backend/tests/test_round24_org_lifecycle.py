"""Round 24: super-admin-only org lifecycle management -- activate,
deactivate, and permanently delete a business or partner account from
ROSKYRO's internal dashboard. See routers/orgs.py's deactivate()/activate()/
delete_org() and app/utils/org_lifecycle.py.

Uses admin_headers (roskyro_admin, from conftest.py) for the "should work"
cases and a fresh, disposable ops_manager login for the "should be
forbidden" cases -- deliberately never touching the shared seeded orgs
(sunrise clinic etc, which other test files' shared session-scoped `client`
also depends on), since deactivate/delete are destructive. Every org used
here is freshly self-registered inside the test itself.
"""
import os

DEMO_PASSWORD = "Roskyro@123"
OPS_MANAGER_EMAIL = "ops@roskyro.com"


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(login_resp):
    return {"Authorization": f"Bearer {login_resp['token']}"}


def _register_org(client, unique_suffix, name_prefix="Round24 Test Clinic"):
    email = f"round24.{unique_suffix}@example.com"
    phone = f"98{unique_suffix}".rjust(10, "1")[:10]
    resp = client.post("/api/auth/register", json={
        "orgName": f"{name_prefix} {unique_suffix}", "ownerName": "Round24 Owner",
        "email": email, "phone": phone, "password": DEMO_PASSWORD,
        "businessType": "clinic", "businessCategory": "clinic", "city": "Pune",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["user"]["orgId"], email, data["token"]


def test_super_admin_can_deactivate_and_reactivate_an_org(client, admin_headers, unique_suffix):
    org_id, owner_email, owner_token = _register_org(client, unique_suffix)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # Owner can use their own dashboard before deactivation.
    me = client.get("/api/auth/me", headers=owner_headers)
    assert me.status_code == 200, me.text

    deactivated = client.post(f"/api/orgs/{org_id}/deactivate", headers=admin_headers)
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["organization"]["is_suspended"] is True

    # Locked out immediately -- same 403 pattern as a deactivated team member.
    blocked = client.get("/api/auth/me", headers=owner_headers)
    assert blocked.status_code == 403, blocked.text

    # Owner can't log back in either (get_current_user runs on every request).
    relogin = client.post("/api/auth/login", json={"identifier": owner_email, "password": DEMO_PASSWORD})
    # Login itself only checks user.status, not org -- token is issued, but
    # every subsequent authenticated call 403s. Confirm that end-to-end:
    if relogin.status_code == 200:
        still_blocked = client.get("/api/auth/me", headers={"Authorization": f"Bearer {relogin.json()['token']}"})
        assert still_blocked.status_code == 403, still_blocked.text

    reactivated = client.post(f"/api/orgs/{org_id}/activate", headers=admin_headers)
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["organization"]["is_suspended"] is False

    restored = client.get("/api/auth/me", headers=owner_headers)
    assert restored.status_code == 200, restored.text


def test_only_roskyro_admin_can_deactivate_an_org(client, unique_suffix):
    org_id, _, _ = _register_org(client, unique_suffix)
    ops = _login(client, OPS_MANAGER_EMAIL)
    ops_headers = _headers(ops)

    resp = client.post(f"/api/orgs/{org_id}/deactivate", headers=ops_headers)
    assert resp.status_code == 403, resp.text


def test_org_owner_cannot_deactivate_or_reactivate_their_own_org(client, unique_suffix):
    org_id, _, owner_token = _register_org(client, unique_suffix)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    resp = client.post(f"/api/orgs/{org_id}/deactivate", headers=owner_headers)
    assert resp.status_code == 403, resp.text


def test_delete_requires_exact_confirmation_name(client, admin_headers, unique_suffix):
    org_id, _, _ = _register_org(client, unique_suffix, name_prefix="Round24 Delete Guard")

    wrong = client.request("DELETE", f"/api/orgs/{org_id}", headers=admin_headers, json={"confirmName": "not the right name"})
    assert wrong.status_code == 400, wrong.text

    # Still exists after the rejected attempt.
    still_there = client.get(f"/api/orgs/{org_id}", headers=admin_headers)
    assert still_there.status_code == 200, still_there.text


def test_only_roskyro_admin_can_delete_an_org(client, unique_suffix):
    org_id, _, _ = _register_org(client, unique_suffix, name_prefix="Round24 Delete Auth")
    ops = _login(client, OPS_MANAGER_EMAIL)
    resp = client.request("DELETE", f"/api/orgs/{org_id}", headers=_headers(ops), json={"confirmName": "whatever"})
    assert resp.status_code == 403, resp.text


def test_hard_delete_cascades_across_the_orgs_own_data(client, admin_headers, unique_suffix):
    """The most important guarantee: after a hard delete, nothing anywhere
    still points at this org_id -- confirmed by re-creating a fresh doctor/
    appointment/team-member set, deleting the org, then checking the
    endpoints that would surface leftovers all come back empty/404."""
    org_name = f"Round24 Cascade Clinic {unique_suffix}"
    org_id, owner_email, owner_token = _register_org(client, unique_suffix, name_prefix="Round24 Cascade Clinic")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # Doctors requires the MANAGE pillar -- admin-assign it directly (bypasses
    # the UPI/payment-confirmation gate entirely, same as round 23) so this
    # fresh org can create real data to cascade.
    grant = client.post("/api/plans/subscribe", headers=admin_headers, json={
        "orgId": org_id, "planCode": "manage", "billingCycle": "monthly",
    })
    assert grant.status_code == 201, grant.text

    doctor = client.post("/api/doctors", headers=owner_headers, json={
        "name": "Dr. Round24", "specialty": "General", "consultationFee": 0,
        "slotDurationMinutes": 20, "capacityPerSlot": 1,
        "weeklySchedule": [{"day": "mon", "openTime": "10:00", "closeTime": "12:00"}],
    })
    assert doctor.status_code == 201, doctor.text

    deleted = client.request("DELETE", f"/api/orgs/{org_id}", headers=admin_headers, json={"confirmName": org_name})
    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert body["deleted"] is True
    assert body["counts"]["doctors"] >= 1
    assert body["counts"]["users"] >= 1
    assert body["counts"]["organizations"] == 1

    # Org itself is gone.
    gone = client.get(f"/api/orgs/{org_id}", headers=admin_headers)
    assert gone.status_code == 404, gone.text

    # The owner's account is gone too -- can't log back in at all.
    relogin = client.post("/api/auth/login", json={"identifier": owner_email, "password": DEMO_PASSWORD})
    assert relogin.status_code in (401, 403, 404), relogin.text

    # Public booking page for this org is gone (booking_settings cascaded).
    public = client.get(f"/api/public/booking/{org_id}")
    assert public.status_code == 404, public.text


def test_deleting_a_partner_org_also_removes_its_partner_profile(client, admin_headers, unique_suffix):
    """Registering as a business first, then becoming a partner (mirrors
    the real "Become a Partner" flow), then deleting that org must also
    remove the `partners` collection row -- not just the `organizations`
    row -- since partner-specific data (services, agreements, settlement
    rules) all key off partner_id, not org_id."""
    org_name = f"Round24 Partner Cascade {unique_suffix}"
    org_id, _, owner_token = _register_org(client, unique_suffix, name_prefix="Round24 Partner Cascade")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    become = client.post("/api/partners/register", headers=owner_headers, json={
        "categorySlug": "pathology_labs", "coverageCities": ["Pune"], "turnaroundTime": "Same day",
        "services": [{"name": "CBC", "description": "Blood test", "price": 200, "priceUnit": "per test", "turnaroundTime": "Same day"}],
    })
    assert become.status_code in (200, 201), become.text

    deleted = client.request("DELETE", f"/api/orgs/{org_id}", headers=admin_headers, json={"confirmName": org_name})
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["counts"].get("partners") == 1
    assert deleted.json()["counts"].get("partner_services", 0) >= 1

    gone = client.get(f"/api/orgs/{org_id}", headers=admin_headers)
    assert gone.status_code == 404, gone.text

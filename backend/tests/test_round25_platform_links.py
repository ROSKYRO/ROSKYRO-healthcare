"""Round 25: "growth hub me esa link section add karde jisse business apne
sare platform ... kuch ek hi jagah se dekh ske ki kya progress hai" -- quick-
access links (Google Business Profile, social media, website, ...) that
ROSKYRO's internal team maintains on a business's behalf, surfaced on that
business's own Growth Hub / Dashboard. See routers/orgs.py's
PUT /orgs/{org_id}/platform-links and routers/dashboard.py's customer
dashboard (`platformLinks`).

Uses admin_headers (roskyro_admin, from conftest.py) and a fresh, disposable
ops_manager login (any internal role should be allowed to manage these, not
just the super admin -- unlike round 24's destructive org lifecycle actions)
for the "should work" cases, plus a freshly self-registered business (never
touching the shared seeded orgs) for the "customer can see but not edit"
checks.
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


def _register_org(client, unique_suffix):
    email = f"round25.{unique_suffix}@example.com"
    phone = f"98{unique_suffix}".rjust(10, "1")[:10]
    resp = client.post("/api/auth/register", json={
        "orgName": f"Round25 Links Clinic {unique_suffix}", "ownerName": "Round25 Owner",
        "email": email, "phone": phone, "password": DEMO_PASSWORD,
        "businessType": "clinic", "businessCategory": "clinic", "city": "Pune",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()
    return data["user"]["orgId"], data["token"]


def _grant_grow(client, admin_headers, org_id):
    resp = client.post("/api/plans/subscribe", headers=admin_headers, json={
        "orgId": org_id, "planCode": "grow", "billingCycle": "monthly",
    })
    assert resp.status_code == 201, resp.text


def test_internal_ops_manager_can_set_platform_links_not_just_super_admin(client, unique_suffix):
    org_id, _ = _register_org(client, unique_suffix)
    ops_headers = _headers(_login(client, OPS_MANAGER_EMAIL))

    resp = client.put(f"/api/orgs/{org_id}/platform-links", headers=ops_headers, json={"links": [
        {"label": "Google Business Profile", "url": "https://g.page/round25-clinic"},
        {"label": "Instagram", "url": "https://instagram.com/round25clinic"},
    ]})
    assert resp.status_code == 200, resp.text
    links = resp.json()["organization"]["platform_links"]
    assert len(links) == 2
    assert links[0]["label"] == "Google Business Profile"
    assert links[0]["url"] == "https://g.page/round25-clinic"
    assert links[0]["id"]  # server-generated id present


def test_business_owner_cannot_set_their_own_platform_links(client, unique_suffix):
    org_id, owner_token = _register_org(client, unique_suffix)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    resp = client.put(f"/api/orgs/{org_id}/platform-links", headers=owner_headers, json={"links": [
        {"label": "Website", "url": "https://example.com"},
    ]})
    assert resp.status_code == 403, resp.text


def test_link_without_label_or_url_is_rejected(client, admin_headers, unique_suffix):
    org_id, _ = _register_org(client, unique_suffix)

    missing_url = client.put(f"/api/orgs/{org_id}/platform-links", headers=admin_headers, json={"links": [
        {"label": "Website", "url": ""},
    ]})
    assert missing_url.status_code == 400, missing_url.text

    missing_label = client.put(f"/api/orgs/{org_id}/platform-links", headers=admin_headers, json={"links": [
        {"label": "", "url": "https://example.com"},
    ]})
    assert missing_label.status_code == 400, missing_label.text


def test_link_with_non_http_url_is_rejected(client, admin_headers, unique_suffix):
    org_id, _ = _register_org(client, unique_suffix)

    resp = client.put(f"/api/orgs/{org_id}/platform-links", headers=admin_headers, json={"links": [
        {"label": "Sketchy", "url": "javascript:alert(1)"},
    ]})
    assert resp.status_code == 400, resp.text


def test_setting_links_on_unknown_org_404s(client, admin_headers):
    resp = client.put("/api/orgs/does-not-exist/platform-links", headers=admin_headers, json={"links": []})
    assert resp.status_code == 404, resp.text


def test_business_dashboard_shows_the_links_roskyro_team_set(client, admin_headers, unique_suffix):
    org_id, owner_token = _register_org(client, unique_suffix)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    _grant_grow(client, admin_headers, org_id)

    put_resp = client.put(f"/api/orgs/{org_id}/platform-links", headers=admin_headers, json={"links": [
        {"label": "Website", "url": "https://round25-clinic.example.com"},
    ]})
    assert put_resp.status_code == 200, put_resp.text

    dash = client.get("/api/dashboard/customer", headers=owner_headers)
    assert dash.status_code == 200, dash.text
    links = dash.json()["platformLinks"]
    assert len(links) == 1
    assert links[0]["label"] == "Website"
    assert links[0]["url"] == "https://round25-clinic.example.com"


def test_business_without_grow_pillar_gets_empty_platform_links_not_an_error(client, unique_suffix):
    org_id, owner_token = _register_org(client, unique_suffix)
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    dash = client.get("/api/dashboard/customer", headers=owner_headers)
    assert dash.status_code == 200, dash.text
    assert dash.json()["platformLinks"] == []


def test_setting_links_replaces_the_previous_list_not_appends(client, admin_headers, unique_suffix):
    org_id, _ = _register_org(client, unique_suffix)

    first = client.put(f"/api/orgs/{org_id}/platform-links", headers=admin_headers, json={"links": [
        {"label": "Instagram", "url": "https://instagram.com/a"},
        {"label": "Facebook", "url": "https://facebook.com/a"},
    ]})
    assert first.status_code == 200, first.text
    assert len(first.json()["organization"]["platform_links"]) == 2

    second = client.put(f"/api/orgs/{org_id}/platform-links", headers=admin_headers, json={"links": [
        {"label": "Website", "url": "https://example.com"},
    ]})
    assert second.status_code == 200, second.text
    links = second.json()["organization"]["platform_links"]
    assert len(links) == 1
    assert links[0]["label"] == "Website"

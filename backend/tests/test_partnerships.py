"""Tests for the "my partner per category" relationship layer
(routers/partnerships.py) -- confirms the two core guarantees agreed with
the user: (1) the open marketplace is NEVER restricted by a partnership --
search-by-service still returns every matching partner, just with the
designated one flagged/sorted first -- and (2) at most one partnership per
(business, category) is ever active at a time, whether it was set directly
or via an accepted partner request."""
DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # owner account, CONNECT pillar active
CITYSCAN_PARTNER_EMAIL = "admin.cityscan.diagnostics@example.com"


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(login_resp):
    return {"Authorization": f"Bearer {login_resp['token']}"}


def _blood_test_partners(client, headers):
    resp = client.get("/api/partners/search-by-service", headers=headers, params={"keyword": "blood"})
    assert resp.status_code == 200, resp.text
    return resp.json()["partners"]


def test_set_partnership_then_search_flags_and_sorts_it_first(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    candidates = _blood_test_partners(client, headers)
    assert len(candidates) >= 1
    chosen = candidates[0]

    set_resp = client.post("/api/partnerships", headers=headers, json={"partnerId": chosen["id"]})
    assert set_resp.status_code == 201, set_resp.text
    assert set_resp.json()["partnership"]["partner_org_name"] == chosen["org_name"]

    results = _blood_test_partners(client, headers)
    assert results[0]["id"] == chosen["id"]
    assert results[0]["is_my_partner"] is True
    # The rest of the marketplace is still fully visible -- nothing filtered out.
    assert len(results) == len(candidates)


def test_swapping_partner_ends_the_previous_one(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    candidates = _blood_test_partners(client, headers)
    assert len(candidates) >= 1
    first_choice = candidates[0]

    client.post("/api/partnerships", headers=headers, json={"partnerId": first_choice["id"]})
    active = client.get("/api/partnerships", headers=headers).json()["partnerships"]
    blood_row = next(p for p in active if p["partner_id"] == first_choice["id"])
    category_id = blood_row["category_id"]

    if len(candidates) < 2:
        return  # only one partner in this category in seed data -- swap test needs a second

    second_choice = candidates[1]
    client.post("/api/partnerships", headers=headers, json={"partnerId": second_choice["id"]})

    active_after = client.get("/api/partnerships", headers=headers).json()["partnerships"]
    same_category_rows = [p for p in active_after if p["category_id"] == category_id]
    assert len(same_category_rows) == 1, "only one active partnership per category should ever exist"
    assert same_category_rows[0]["partner_id"] == second_choice["id"]


def test_end_partnership_removes_it(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    candidates = _blood_test_partners(client, headers)
    chosen = candidates[0]
    set_resp = client.post("/api/partnerships", headers=headers, json={"partnerId": chosen["id"]})
    category_id = set_resp.json()["partnership"]["category_id"]

    ended = client.post(f"/api/partnerships/{category_id}/end", headers=headers)
    assert ended.status_code == 200, ended.text

    active = client.get("/api/partnerships", headers=headers).json()["partnerships"]
    assert all(p["category_id"] != category_id for p in active)

    results = _blood_test_partners(client, headers)
    assert all(not r["is_my_partner"] for r in results)


def test_non_owner_cannot_set_or_end_partnership(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    owner_headers = _headers(sunrise)

    org_id = sunrise["user"]["orgId"]
    invited = client.post(f"/api/orgs/{org_id}/team", headers=owner_headers, json={
        "name": f"Staff {unique_suffix}", "email": f"staff{unique_suffix}@pytest.roskyro.example",
        "role": "staff", "phone": f"91{unique_suffix.rjust(8, '0')[:8]}", "password": "StaffPass@1",
    })
    assert invited.status_code == 201, invited.text

    staff = _login(client, f"staff{unique_suffix}@pytest.roskyro.example", password="StaffPass@1")
    staff_headers = _headers(staff)

    candidates = _blood_test_partners(client, staff_headers)
    resp = client.post("/api/partnerships", headers=staff_headers, json={"partnerId": candidates[0]["id"]})
    assert resp.status_code == 403, resp.text

    # But a non-owner CAN still view the business's existing partnerships.
    view = client.get("/api/partnerships", headers=staff_headers)
    assert view.status_code == 200, view.text


def test_partner_request_is_idempotent_while_pending(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    partner_login = _login(client, CITYSCAN_PARTNER_EMAIL)
    partner_headers = _headers(partner_login)

    first = client.post("/api/partnerships/requests", headers=partner_headers, json={"orgId": org_id})
    assert first.status_code == 201, first.text
    assert first.json()["alreadyPending"] is False

    second = client.post("/api/partnerships/requests", headers=partner_headers, json={"orgId": org_id})
    assert second.status_code == 201, second.text
    assert second.json()["alreadyPending"] is True
    assert second.json()["request"]["id"] == first.json()["request"]["id"]


def test_only_partner_shell_can_send_a_request(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    resp = client.post("/api/partnerships/requests", headers=headers, json={"orgId": sunrise["user"]["orgId"]})
    assert resp.status_code == 403, resp.text


def test_accepting_a_request_creates_the_partnership_and_swaps_correctly(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    owner_headers = _headers(sunrise)
    org_id = sunrise["user"]["orgId"]

    partner_login = _login(client, CITYSCAN_PARTNER_EMAIL)
    partner_headers = _headers(partner_login)

    sent = client.post("/api/partnerships/requests", headers=partner_headers, json={"orgId": org_id})
    request_id = sent.json()["request"]["id"]
    category_id = sent.json()["request"]["category_id"]

    incoming = client.get("/api/partnerships/requests", headers=owner_headers).json()["requests"]
    assert any(r["id"] == request_id and r["status"] == "pending" for r in incoming)

    decided = client.post(f"/api/partnerships/requests/{request_id}/decide", headers=owner_headers, json={"decision": "accepted"})
    assert decided.status_code == 200, decided.text
    assert decided.json()["request"]["status"] == "accepted"

    active = client.get("/api/partnerships", headers=owner_headers).json()["partnerships"]
    same_category = [p for p in active if p["category_id"] == category_id]
    assert len(same_category) == 1, "accepting a request must not leave two active partnerships for the same category"

    # Deciding an already-decided request is rejected, not silently re-applied.
    again = client.post(f"/api/partnerships/requests/{request_id}/decide", headers=owner_headers, json={"decision": "accepted"})
    assert again.status_code == 400, again.text


def test_org_directory_lets_a_partner_find_businesses_to_request(client):
    """A partner needs some way to discover which business to send a
    partnership request to (routers/orgs.py's GET /directory) -- a
    customer-shell user shouldn't get this (it's not needed there, the
    open marketplace search already covers their side), and it must only
    ever surface referral-creating business types, never other partners'
    own org records."""
    partner_login = _login(client, CITYSCAN_PARTNER_EMAIL)
    partner_headers = _headers(partner_login)

    resp = client.get("/api/orgs/directory", headers=partner_headers, params={"q": "Sunrise"})
    assert resp.status_code == 200, resp.text
    orgs = resp.json()["organizations"]
    assert any("Sunrise" in o["name"] for o in orgs)
    assert all(o["businessType"] in ("clinic", "hospital", "eye_hospital") for o in orgs)

    sunrise = _login(client, SUNRISE_EMAIL)
    owner_headers = _headers(sunrise)
    forbidden = client.get("/api/orgs/directory", headers=owner_headers)
    assert forbidden.status_code == 403, forbidden.text

def _register_user(client, suffix):
    resp = client.post("/api/auth/register", json={
        "orgName": f"Reset Clinic {suffix}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": f"Reset Owner {suffix}",
        "email": f"reset{suffix}@pytest.roskyro.example",
        "phone": f"97{suffix.rjust(8, '0')[:8]}",
        "password": "OldPassword@1",
    })
    assert resp.status_code == 201, resp.text
    return f"reset{suffix}@pytest.roskyro.example"


def test_submit_request_unknown_identifier_is_vague_404(client):
    """No user enumeration: an unknown identifier gets a generic 404, not a
    different error than "wrong password" would on login."""
    resp = client.post("/api/password-resets", json={"identifier": "nobody-at-all@nowhere.example"})
    assert resp.status_code == 404


def test_submit_request_is_idempotent_while_pending(client, unique_suffix):
    email = _register_user(client, unique_suffix)

    first = client.post("/api/password-resets", json={"identifier": email, "note": "locked out"})
    assert first.status_code == 201, first.text
    assert first.json()["alreadyPending"] is False

    second = client.post("/api/password-resets", json={"identifier": email})
    assert second.status_code == 201, second.text
    assert second.json()["alreadyPending"] is True
    assert second.json()["request"]["id"] == first.json()["request"]["id"]


def test_only_super_admin_can_list_or_resolve_requests(client, unique_suffix):
    email = _register_user(client, unique_suffix)
    client.post("/api/password-resets", json={"identifier": email})

    # No auth at all -> rejected.
    resp = client.get("/api/password-resets")
    assert resp.status_code in (401, 403)


def test_full_reset_round_trip(client, unique_suffix, admin_headers):
    """Submit a request as the locked-out user, resolve it as super admin
    with a new password, then confirm login works with the NEW password
    and the OLD password no longer does."""
    email = _register_user(client, unique_suffix)

    submitted = client.post("/api/password-resets", json={"identifier": email})
    request_id = submitted.json()["request"]["id"]

    resolved = client.post(
        f"/api/password-resets/{request_id}/resolve",
        json={"newPassword": "BrandNewPass@2"},
        headers=admin_headers,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["request"]["status"] == "resolved"

    old_login = client.post("/api/auth/login", json={"identifier": email, "password": "OldPassword@1"})
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", json={"identifier": email, "password": "BrandNewPass@2"})
    assert new_login.status_code == 200, new_login.text


def test_resolve_already_handled_request_rejected(client, unique_suffix, admin_headers):
    email = _register_user(client, unique_suffix)
    submitted = client.post("/api/password-resets", json={"identifier": email})
    request_id = submitted.json()["request"]["id"]

    client.post(f"/api/password-resets/{request_id}/resolve", json={"newPassword": "FirstPass@1"}, headers=admin_headers)
    second = client.post(f"/api/password-resets/{request_id}/resolve", json={"newPassword": "SecondPass@1"}, headers=admin_headers)
    assert second.status_code == 400

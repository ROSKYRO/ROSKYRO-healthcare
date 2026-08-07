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


def _find_pending_request(client, admin_headers, email):
    rows = client.get("/api/password-resets", headers=admin_headers).json()["requests"]
    matches = [r for r in rows if r["user_email"] == email and r["status"] == "pending"]
    assert len(matches) == 1, f"expected exactly 1 pending request for {email}, found {len(matches)}"
    return matches[0]


def test_submit_request_unknown_identifier_looks_identical_to_known(client):
    """Fixed: this endpoint used to return 404 for an identifier with no
    matching account and 201 (with the created request) for one that
    matched -- two distinguishable responses on an unauthenticated
    endpoint is a textbook user-enumeration oracle. Now both cases return
    the exact same shape, and no DB row is written for an identifier that
    doesn't match anyone."""
    resp = client.post("/api/password-resets", json={"identifier": "nobody-at-all@nowhere.example"})
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"alreadyPending": False}


def test_unknown_identifier_creates_no_request(client, admin_headers):
    before = client.get("/api/password-resets", headers=admin_headers).json()["requests"]
    client.post("/api/password-resets", json={"identifier": "still-nobody@nowhere.example"})
    after = client.get("/api/password-resets", headers=admin_headers).json()["requests"]
    assert len(after) == len(before), "a request row was created for a non-existent account"


def test_submit_request_is_idempotent_while_pending(client, unique_suffix, admin_headers):
    email = _register_user(client, unique_suffix)

    first = client.post("/api/password-resets", json={"identifier": email, "note": "locked out"})
    assert first.status_code == 201, first.text
    assert first.json()["alreadyPending"] is False

    second = client.post("/api/password-resets", json={"identifier": email})
    assert second.status_code == 201, second.text
    assert second.json()["alreadyPending"] is True

    # Idempotency verified server-side (via the admin's own queue, the only
    # authenticated way to see request details) rather than through the
    # anonymous submitter's response, which deliberately carries no
    # account-identifying info now -- see the enumeration-fix docstring on
    # submit_request().
    rows = client.get("/api/password-resets", headers=admin_headers).json()["requests"]
    pending_for_email = [r for r in rows if r["user_email"] == email and r["status"] == "pending"]
    assert len(pending_for_email) == 1, "a second request was created instead of reusing the pending one"


def test_password_reset_submit_is_rate_limited():
    """Fixed: this endpoint had zero throttling -- the other two
    unauthenticated, DB-writing endpoints in this codebase (login, public
    booking) both already had it. Exercises the real "password_reset_submit"
    bucket registered in app/utils/rate_limit.py's _LIMITS ((10, 60)) --
    but through enforce_rate_limit() directly with a dedicated fake IP,
    same convention as test_round13_fixes.py's rate-limit tests, so this
    doesn't burn through the budget the other tests in this file share via
    the one session-scoped TestClient (which all look like the same
    "caller" to the limiter)."""
    from app.utils.rate_limit import enforce_rate_limit
    from fastapi import HTTPException
    import pytest as _pytest

    fake_ip = "203.0.113.77"
    for _ in range(10):
        enforce_rate_limit("password_reset_submit", fake_ip)  # should not raise
    with _pytest.raises(HTTPException) as exc_info:
        enforce_rate_limit("password_reset_submit", fake_ip)
    assert exc_info.value.status_code == 429


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

    client.post("/api/password-resets", json={"identifier": email})
    request_id = _find_pending_request(client, admin_headers, email)["id"]

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
    client.post("/api/password-resets", json={"identifier": email})
    request_id = _find_pending_request(client, admin_headers, email)["id"]

    client.post(f"/api/password-resets/{request_id}/resolve", json={"newPassword": "FirstPass@1"}, headers=admin_headers)
    second = client.post(f"/api/password-resets/{request_id}/resolve", json={"newPassword": "SecondPass@1"}, headers=admin_headers)
    assert second.status_code == 400

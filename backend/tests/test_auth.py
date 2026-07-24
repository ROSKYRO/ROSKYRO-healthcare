import pytest


def _register(client, suffix, password="Testpass@123"):
    return client.post("/api/auth/register", json={
        "orgName": f"Pytest Clinic {suffix}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": f"Owner {suffix}",
        "email": f"owner{suffix}@pytest.roskyro.example",
        "phone": f"98{suffix.rjust(8, '0')[:8]}",
        "password": password,
    })


def test_register_then_login_with_email(client, unique_suffix):
    reg = _register(client, unique_suffix)
    assert reg.status_code == 201, reg.text
    email = f"owner{unique_suffix}@pytest.roskyro.example"

    login = client.post("/api/auth/login", json={"identifier": email, "password": "Testpass@123"})
    assert login.status_code == 200, login.text
    body = login.json()
    assert "token" in body and body["token"]
    assert body["user"]["email"] == email


def test_login_with_mobile_number_any_format_matches(client, unique_suffix):
    """normalize_phone() should make '+91-98xxxxxxx', '98xxxxxxx' etc. all
    resolve to the same stored account."""
    reg = _register(client, unique_suffix)
    assert reg.status_code == 201, reg.text
    phone = f"98{unique_suffix.rjust(8, '0')[:8]}"

    login = client.post("/api/auth/login", json={"identifier": f"+91-{phone}", "password": "Testpass@123"})
    assert login.status_code == 200, login.text


def test_login_wrong_password_rejected(client, unique_suffix):
    _register(client, unique_suffix)
    email = f"owner{unique_suffix}@pytest.roskyro.example"
    login = client.post("/api/auth/login", json={"identifier": email, "password": "WrongPassword!"})
    assert login.status_code == 401
    assert "error" in login.json()


def test_login_unknown_identifier_rejected(client):
    login = client.post("/api/auth/login", json={"identifier": "nobody@nowhere.example", "password": "whatever"})
    assert login.status_code == 401


def test_register_duplicate_email_rejected(client, unique_suffix):
    first = _register(client, unique_suffix)
    assert first.status_code == 201, first.text
    dup = _register(client, unique_suffix)
    assert dup.status_code == 409


def test_admin_login_from_env_credentials(admin_token):
    """Confirms ADMIN_EMAIL/ADMIN_PASSWORD bootstrap (app/admin_bootstrap.py)
    actually produces a working super-admin login on a fresh boot."""
    assert admin_token

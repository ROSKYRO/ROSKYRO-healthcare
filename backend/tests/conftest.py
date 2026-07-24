"""Shared pytest fixtures for the ROSKYRO Healthcare OS backend.

Runs against mongomock-motor (USE_MOCK_DB=true), never a real MongoDB --
these tests are meant to run anywhere (a laptop, CI, Railway's build step)
with zero external services. The env vars below MUST be set before
`app.*` is imported anywhere (config.py reads them at import time via
os.getenv), so this file sets them at module load, ahead of any `from app
import ...`.

The `client` fixture is session-scoped: FastAPI's startup events (mock-DB
seed + super-admin bootstrap, see app/main.py) run exactly once, the same
way a real deployment boots once and stays up. Tests that mutate data use
their own uniquely-generated emails/phones (see `unique_suffix`) so they
don't stomp on each other or on the seeded demo data.
"""
import os

os.environ.setdefault("USE_MOCK_DB", "true")
os.environ.setdefault("MONGODB_DB", "roskyro_test")
os.environ.setdefault("JWT_SECRET", "pytest_test_secret_do_not_use_in_prod")
os.environ.setdefault("ADMIN_EMAIL", "admin@roskyro.com")
os.environ.setdefault("ADMIN_PASSWORD", "Roskyro@123")
os.environ.setdefault("CLIENT_ORIGIN", "http://localhost:3000")

import itertools
import pytest
from fastapi.testclient import TestClient

from app.main import app

_suffix_counter = itertools.count(1)


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def unique_suffix():
    """A short, test-run-unique string for building collision-free emails
    and phone numbers, since the session-scoped client shares one
    in-memory DB across every test in the run."""
    return f"{next(_suffix_counter)}{os.getpid() % 10000}"


@pytest.fixture()
def admin_token(client):
    resp = client.post("/api/auth/login", json={
        "identifier": os.environ["ADMIN_EMAIL"],
        "password": os.environ["ADMIN_PASSWORD"],
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


@pytest.fixture()
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

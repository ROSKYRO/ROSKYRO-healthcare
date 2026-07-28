"""Regression tests for round 13's fixes:

1. auth.py's RegisterBody had no minimum password length -- Register.jsx
   enforces minLength={6} client-side only, so anyone calling
   POST /api/auth/register directly could create a real account with an
   empty/1-character password, completely bypassing the intended policy.
   Fixed with Field(min_length=6) on the pydantic model.

2. POST /api/auth/login had no rate limiting at all -- unlimited password
   guesses per IP with no lockout/backoff/429 anywhere. Fixed by wiring in
   the existing per-IP sliding-window limiter (utils/rate_limit.py),
   deliberately scoped to only count FAILED attempts (wrong identifier or
   wrong password) -- a blanket per-call limit would also throttle
   legitimate high-frequency successful logins (several staff behind one
   shared clinic IP, or this very test suite, which logs in dozens of
   times per run with valid credentials).

3. utils/booking.py's upcoming_dates() computed "today" from
   datetime.utcnow().date() -- plain UTC, not the clinic's actual local
   (IST) day. For the ~5.5 hours of every day between UTC midnight and
   IST midnight (00:00-05:29 IST == still "yesterday" in UTC), this made
   the public self-booking calendar (and the same function's use in
   re-validating a submitted booking date) think "today" was the PREVIOUS
   day -- letting a patient book, and the backend accept, an appointment
   for a date that had already closed out operationally for the clinic.
   Fixed by computing "today" against the clinic's IST wall-clock day.
"""
import importlib
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.utils.rate_limit import enforce_rate_limit


def _register(client, suffix, password="Testpass@123"):
    return client.post("/api/auth/register", json={
        "orgName": f"Round13 Clinic {suffix}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": f"Owner {suffix}",
        "email": f"round13owner{suffix}@pytest.roskyro.example",
        "phone": f"97{suffix.rjust(8, '0')[:8]}",
        "password": password,
    })


# ---------------------------------------------------------------------------
# auth.py -- RegisterBody password minimum length
# ---------------------------------------------------------------------------

def test_register_rejects_too_short_password(client, unique_suffix):
    resp = _register(client, unique_suffix, password="ab")
    assert resp.status_code == 422, resp.text


def test_register_rejects_empty_password(client, unique_suffix):
    resp = _register(client, unique_suffix, password="")
    assert resp.status_code == 422, resp.text


def test_register_accepts_six_character_password(client, unique_suffix):
    resp = _register(client, unique_suffix, password="abcdef")
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# rate_limit.py -- underlying sliding-window mechanism (isolated bucket,
# not the shared "auth_login_failed" bucket -- keeps this test from
# poisoning the rate-limit budget any other test in the same run relies on
# seeing a normal 401 rather than a 429).
# ---------------------------------------------------------------------------

def test_enforce_rate_limit_blocks_after_limit_exceeded():
    bucket = "test_round13_isolated_bucket"
    ip = "203.0.113.5"
    # Unknown bucket names fall back to the default (20 requests / 60s) --
    # see rate_limit.py's _LIMITS.get(bucket, (20, 60)).
    for _ in range(20):
        enforce_rate_limit(bucket, ip)  # should not raise
    with pytest.raises(HTTPException) as exc_info:
        enforce_rate_limit(bucket, ip)
    assert exc_info.value.status_code == 429


def test_enforce_rate_limit_is_per_ip():
    bucket = "test_round13_per_ip_bucket"
    for _ in range(20):
        enforce_rate_limit(bucket, "198.51.100.1")
    # A different IP under the same bucket must not be affected by the
    # first IP's usage.
    enforce_rate_limit(bucket, "198.51.100.2")  # should not raise


# ---------------------------------------------------------------------------
# auth.py -- login() only rate-limits FAILED attempts, never successes
# ---------------------------------------------------------------------------

def test_repeated_successful_logins_are_never_rate_limited(client, unique_suffix):
    """The core regression this round introduced and then fixed within the
    same round: a blanket per-call limit on /api/auth/login broke this
    project's own test suite (dozens of legitimate successful logins
    within the same 60s window). Confirms MANY successful logins in a row
    -- well past what any per-call limit would have allowed -- all still
    succeed, because only failures count toward the limit."""
    reg = _register(client, unique_suffix)
    assert reg.status_code == 201, reg.text
    email = f"round13owner{unique_suffix}@pytest.roskyro.example"

    for _ in range(25):
        resp = client.post("/api/auth/login", json={"identifier": email, "password": "Testpass@123"})
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# booking.py -- IST-day fix
# ---------------------------------------------------------------------------

def test_upcoming_dates_uses_ist_day_not_utc_day(monkeypatch):
    """Directly exercises the exact pre-fix failure window: a UTC moment
    that is still "yesterday" in UTC but already "today" in IST (any time
    between 18:30 UTC and 23:59 UTC, i.e. 00:00-05:29 IST the next day)."""
    from app.utils import booking as booking_module

    class FixedDateTime(datetime):
        @classmethod
        def utcnow(cls):
            # 2026-07-28 20:30 UTC == 2026-07-29 02:00 IST.
            return cls(2026, 7, 28, 20, 30, 0)

    monkeypatch.setattr(booking_module, "datetime", FixedDateTime)
    dates = booking_module.upcoming_dates(3)
    assert dates[0] == "2026-07-29", (
        f"expected today's IST calendar date (2026-07-29) as the first entry, got {dates[0]}"
    )
    assert dates == ["2026-07-29", "2026-07-30", "2026-07-31"]


def test_upcoming_dates_unaffected_mid_day(monkeypatch):
    """Sanity check: a UTC moment that's unambiguously the same calendar
    day in both UTC and IST must still produce that same day (guards
    against the fix overcorrecting)."""
    from app.utils import booking as booking_module

    class FixedDateTime(datetime):
        @classmethod
        def utcnow(cls):
            # 2026-07-28 10:00 UTC == 2026-07-28 15:30 IST -- same day either way.
            return cls(2026, 7, 28, 10, 0, 0)

    monkeypatch.setattr(booking_module, "datetime", FixedDateTime)
    dates = booking_module.upcoming_dates(2)
    assert dates == ["2026-07-28", "2026-07-29"]

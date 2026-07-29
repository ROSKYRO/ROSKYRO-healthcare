"""Regression tests for round 9's fix:

booking_settings.py's PATCH /booking-settings accepted isEnabled and
bookingWindowDays with zero validation, and both feed the PUBLIC
(unauthenticated, patient-facing) booking router the moment they're bad:

- bookingWindowDays flows straight into utils/booking.py's
  upcoming_dates(), which does `range(int(window_days))` -- a non-numeric
  value crashes with an unhandled ValueError, taking down the public
  availability/booking endpoints for every doctor at that business.
- isEnabled is checked in public_booking.py as `not settings.get(
  "is_enabled")` -- in Python the STRING "false" is truthy, so a client
  that sends {"isEnabled": "false"} (not a real JSON boolean) would leave
  booking ENABLED, the opposite of what was just "saved" as off.
"""
import pytest

from app.utils.booking import MAX_BOOKING_WINDOW_DAYS, upcoming_dates

DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _login_full(client, identifier, password=DEMO_PASSWORD):
    """Like _login, but also returns the org id from the same login
    response's `user.orgId` (public_user() in auth.py renames org_id ->
    orgId) -- avoids a second round-trip just to learn the caller's org."""
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["user"]["orgId"]


def test_upcoming_dates_survives_non_numeric_window():
    """SUPERSEDED in round 18. This test previously asserted that
    upcoming_dates("abc") RAISES ValueError -- it documented the downstream
    crash that round 9's HTTP-level validation (test_patch_booking_settings_
    rejects_non_numeric_window_days, below, still passing) was added to
    prevent.

    Round 18 made the helper itself defensive as a second layer, because the
    write-side validator only protects rows written AFTER it shipped: a row
    already sitting in the production database from before round 9 would
    still take down the PUBLIC, unauthenticated patient booking page with a
    raw 500 for that entire business. It now falls back to the 7-day default
    instead of raising, and the window is additionally clamped to the same
    1..60 range the Booking Settings form enforces client-side.

    The round-9 guarantee is unchanged and still asserted below: bad input
    is rejected at the API with a 400 and never stored."""
    assert len(upcoming_dates("abc")) == 7
    assert len(upcoming_dates(None)) == 7
    # Clamped, not obeyed -- a pre-existing row saying 100000 must not make
    # the public availability endpoint build 100,000 day entries per request.
    assert len(upcoming_dates(100000)) == MAX_BOOKING_WINDOW_DAYS
    assert len(upcoming_dates(0)) == 1


def test_patch_booking_settings_rejects_non_numeric_window_days(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.patch("/api/booking-settings", headers=headers, json={"bookingWindowDays": "abc"})
    assert resp.status_code == 400, resp.text
    assert "whole number" in resp.json()["error"].lower()


def test_patch_booking_settings_rejects_zero_or_negative_window_days(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.patch("/api/booking-settings", headers=headers, json={"bookingWindowDays": 0})
    assert resp.status_code == 400, resp.text


def test_patch_booking_settings_accepts_numeric_string_window_days(client):
    """A numeric-looking value must still work -- only genuinely invalid
    values should be rejected (same lenient-but-safe coercion pattern used
    for doctors.py's consultationFee fix in an earlier round)."""
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.patch("/api/booking-settings", headers=headers, json={"bookingWindowDays": "14"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["settings"]["booking_window_days"] == 14


def test_patch_booking_settings_rejects_non_boolean_is_enabled_string(client):
    """The specific inverted-logic bug: {"isEnabled": "false"} must be
    REJECTED, not silently accepted as if it correctly disabled booking
    (a non-empty string is truthy in Python, so pre-fix this would have
    stored a value that public_booking.py reads back as "still enabled")."""
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.patch("/api/booking-settings", headers=headers, json={"isEnabled": "false"})
    assert resp.status_code == 400, resp.text
    assert "true or false" in resp.json()["error"].lower()


def test_patch_booking_settings_accepts_real_booleans(client):
    headers = _login(client, SUNRISE_EMAIL)
    on = client.patch("/api/booking-settings", headers=headers, json={"isEnabled": True})
    assert on.status_code == 200, on.text
    assert on.json()["settings"]["is_enabled"] is True

    off = client.patch("/api/booking-settings", headers=headers, json={"isEnabled": False})
    assert off.status_code == 200, off.text
    assert off.json()["settings"]["is_enabled"] is False


def test_public_booking_respects_disabled_setting_end_to_end(client):
    """Full end-to-end check: after PATCHing isEnabled=False, the public
    (unauthenticated) booking page for this org must actually report
    booking as closed -- this is the real-world behavior the isEnabled
    validation fix protects."""
    headers, org_id = _login_full(client, SUNRISE_EMAIL)

    client.patch("/api/booking-settings", headers=headers, json={"isEnabled": False})
    public_resp = client.get(f"/api/public/booking/{org_id}")
    assert public_resp.status_code == 404, public_resp.text

    # restore enabled so this test doesn't leave the org's public booking
    # page broken for any test/usage that runs after it in this shared DB.
    client.patch("/api/booking-settings", headers=headers, json={"isEnabled": True})

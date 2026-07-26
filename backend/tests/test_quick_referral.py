"""Tests for the quick-referral building blocks: the unique one-time QR
booking code (routers/public_booking.py) + its org-scoped lookup
(routers/appointments.py's GET /lookup/{booking_code}), and the
keyword-across-services partner search (routers/partners.py's GET
/search-by-service) -- together these power ReferralNew.jsx's
type-a-code / type-a-keyword / click-a-partner quick referral flow."""
DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # has MANAGE (appointments) + CONNECT (referrals) pillars
VITAL_SKIN_EMAIL = "vital.skin...aesthetics@example.com"  # also has MANAGE -- used to prove org-scoping


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(login_resp):
    return {"Authorization": f"Bearer {login_resp['token']}"}


def _book_via_qr(client, org_id):
    doctors = client.get(f"/api/public/booking/{org_id}").json()["doctors"]
    doctor_id = doctors[0]["id"]
    avail = client.get(f"/api/public/booking/{org_id}/doctors/{doctor_id}/availability").json()
    day = next(d for d in avail["days"] if any(s["remaining"] > 0 for s in d["slots"]))
    slot = next(s for s in day["slots"] if s["remaining"] > 0)
    resp = client.post(f"/api/public/booking/{org_id}/book", json={
        "patientName": "Quick Referral QR Patient", "patientPhone": "9911100022",
        "doctorId": doctor_id, "appointmentDate": day["date"], "appointmentTime": slot["time"],
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_qr_booking_gets_a_unique_booking_code(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]

    first = _book_via_qr(client, org_id)
    second = _book_via_qr(client, org_id)
    assert first["bookingCode"].startswith("BK-")
    assert second["bookingCode"].startswith("BK-")
    assert first["bookingCode"] != second["bookingCode"]


def test_lookup_by_booking_code_fills_patient_details(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    booked = _book_via_qr(client, org_id)
    code = booked["bookingCode"]

    resp = client.get(f"/api/appointments/lookup/{code}", headers=_headers(sunrise))
    assert resp.status_code == 200, resp.text
    appt = resp.json()["appointment"]
    assert appt["patient_name"] == "Quick Referral QR Patient"
    assert appt["patient_phone"] == "9911100022"

    # Lowercase input still matches (normalized server-side).
    resp_lower = client.get(f"/api/appointments/lookup/{code.lower()}", headers=_headers(sunrise))
    assert resp_lower.status_code == 200, resp_lower.text


def test_lookup_is_scoped_to_the_booking_own_business(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    booked = _book_via_qr(client, org_id)

    other_business = _login(client, VITAL_SKIN_EMAIL)
    resp = client.get(f"/api/appointments/lookup/{booked['bookingCode']}", headers=_headers(other_business))
    assert resp.status_code == 404, resp.text


def test_lookup_unknown_code_is_404(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    resp = client.get("/api/appointments/lookup/BK-999999", headers=_headers(sunrise))
    assert resp.status_code == 404, resp.text


def test_manually_created_appointment_has_no_booking_code_to_look_up(client):
    """Confirms the "no booking id -> fill it in by hand" fallback: a
    front-desk-entered (non-QR) appointment never gets a booking_code, so
    it deliberately can't be pulled up this way."""
    sunrise = _login(client, SUNRISE_EMAIL)
    created = client.post("/api/appointments", headers=_headers(sunrise), json={
        "patientName": "Manual Walkin Patient", "appointmentDate": "2026-08-01",
    })
    assert created.status_code == 201, created.text
    assert created.json()["appointment"].get("booking_code") is None


def test_search_by_service_matches_category_and_named_services(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)

    blood = client.get("/api/partners/search-by-service", headers=headers, params={"keyword": "blood"})
    assert blood.status_code == 200, blood.text
    assert len(blood.json()["partners"]) > 0

    gibberish = client.get("/api/partners/search-by-service", headers=headers, params={"keyword": "zzzznotarealservicezzz"})
    assert gibberish.status_code == 200, gibberish.text
    assert gibberish.json()["partners"] == []

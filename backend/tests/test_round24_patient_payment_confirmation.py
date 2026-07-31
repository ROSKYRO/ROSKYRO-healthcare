"""Round 24: a patient's QR self-booking payment is entirely self-reported
(the patient clicks "Maine Payment Kar Diya" over a payment the CLINIC's own
UPI account receives -- ROSKYRO never sees that transaction). So a fee>0
booking must start life as payment_status "pending" and only the clinic's
own staff -- who can actually see the money land -- can confirm it via
PATCH /api/appointments/{id} {paymentStatus: "paid"}. This mirrors round 23's
business/partner subscription gate, but the confirming authority here is the
clinic itself, not ROSKYRO's roskyro_admin, since the money never touches a
ROSKYRO-controlled account.

See routers/public_booking.py's book_slot() and routers/appointments.py's
patch_appointment().

NOTE: public_booking.py's book_slot() is rate-limited at 10 requests/60s per
IP (app/utils/rate_limit.py's "public_booking" bucket), and that limiter is a
single process-wide in-memory dict shared by the ENTIRE test session (the
`client` fixture is session-scoped) -- every other test file that calls this
endpoint (test_quick_referral.py, test_round18_fixes.py, test_round6_fixes.py)
draws from the same budget. So this file deliberately keeps its own booking
count as low as possible, combining multiple assertions onto one booking
wherever the assertions don't conflict, instead of one booking per test.
"""
DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # has MANAGE (appointments), doctors with fee > 0
VITAL_SKIN_EMAIL = "vital.skin...aesthetics@example.com"  # separate org, also has MANAGE


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(login_resp):
    return {"Authorization": f"Bearer {login_resp['token']}"}


def _fee_doctor(client, org_id):
    """First active doctor at this org with a consultation fee > 0."""
    doctors = client.get(f"/api/public/booking/{org_id}").json()["doctors"]
    fee_doctor = next((d for d in doctors if d["consultationFee"] > 0), None)
    assert fee_doctor is not None, "seeded org must have at least one fee>0 doctor for this test"
    return fee_doctor


def _open_slot(client, org_id, doctor_id):
    avail = client.get(f"/api/public/booking/{org_id}/doctors/{doctor_id}/availability").json()
    day = next(d for d in avail["days"] if any(s["remaining"] > 0 for s in d["slots"]))
    slot = next(s for s in day["slots"] if s["remaining"] > 0)
    return day["date"], slot["time"], next(s for s in day["slots"] if s["time"] == slot["time"])["remaining"]


def _book(client, org_id, doctor_id, date, time, phone):
    resp = client.post(f"/api/public/booking/{org_id}/book", json={
        "patientName": "Round24 Patient", "patientPhone": phone,
        "doctorId": doctor_id, "appointmentDate": date, "appointmentTime": time,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_fee_booking_starts_pending_and_still_occupies_slot_capacity(client):
    """One booking, two things checked: (1) it starts payment_status
    "pending" (not auto-"paid") with a token already issued, and (2) it
    still counts against slot capacity while unconfirmed -- otherwise two
    patients could be issued the same slot/token before the first claim is
    ever verified."""
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    doctor = _fee_doctor(client, org_id)
    date, time, remaining_before = _open_slot(client, org_id, doctor["id"])

    result = _book(client, org_id, doctor["id"], date, time, "9800012401")

    assert result["appointment"]["payment_status"] == "pending"
    assert result["tokenNumber"] >= 1
    assert result["payment"]["collected"] is True
    assert result["payment"]["pending"] is True

    avail_after = client.get(f"/api/public/booking/{org_id}/doctors/{doctor['id']}/availability").json()
    day_after = next(d for d in avail_after["days"] if d["date"] == date)
    remaining_after = next(s for s in day_after["slots"] if s["time"] == time)["remaining"]
    assert remaining_after == remaining_before - 1


def test_free_doctor_booking_needs_no_confirmation(client):
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    doctors = client.get(f"/api/public/booking/{org_id}").json()["doctors"]
    free_doctor = next((d for d in doctors if d["consultationFee"] == 0), None)
    if not free_doctor:
        return  # this seeded org has no free doctor -- nothing to assert
    date, time, _ = _open_slot(client, org_id, free_doctor["id"])
    result = _book(client, org_id, free_doctor["id"], date, time, "9800012402")
    assert result["appointment"]["payment_status"] == "not_required"
    assert result["payment"]["collected"] is False
    assert result["payment"]["pending"] is False


def test_clinic_confirms_payment_and_reconfirming_is_harmless(client):
    """One booking: the clinic confirms it (flips pending -> paid), then
    confirms again to prove that's harmless (no separate confirm/reject
    pair here like round 23's plan subscriptions -- just a status flip the
    clinic controls directly, so re-confirming just no-ops safely)."""
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    org_id = sunrise["user"]["orgId"]
    doctor = _fee_doctor(client, org_id)
    date, time, _ = _open_slot(client, org_id, doctor["id"])
    result = _book(client, org_id, doctor["id"], date, time, "9800012403")
    appointment_id = result["appointment"]["id"]

    first = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"paymentStatus": "paid"})
    assert first.status_code == 200, first.text
    assert first.json()["appointment"]["payment_status"] == "paid"

    second = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"paymentStatus": "paid"})
    assert second.status_code == 200, second.text
    assert second.json()["appointment"]["payment_status"] == "paid"


def test_another_org_cannot_confirm_this_clinics_patient_payment(client):
    """A patient's payment confirmation right belongs only to the clinic
    that actually received the UPI payment -- not ROSKYRO, not any other
    business on the platform. Reuses the same ownership check every other
    appointments.py IDOR fix already relies on."""
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    doctor = _fee_doctor(client, org_id)
    date, time, _ = _open_slot(client, org_id, doctor["id"])
    result = _book(client, org_id, doctor["id"], date, time, "9800012404")
    appointment_id = result["appointment"]["id"]

    vital_skin = _login(client, VITAL_SKIN_EMAIL)
    other_headers = _headers(vital_skin)
    resp = client.patch(f"/api/appointments/{appointment_id}", headers=other_headers, json={"paymentStatus": "paid"})
    assert resp.status_code == 403, resp.text

    # Confirm it's still pending after the rejected attempt.
    still_pending = client.get("/api/appointments", headers=_headers(sunrise)).json()["appointments"]
    row = next(a for a in still_pending if a["id"] == appointment_id)
    assert row["payment_status"] == "pending"

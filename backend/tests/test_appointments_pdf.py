"""Tests for the per-day paid-appointments PDF export. Available to any
business using the appointment booking system (MANAGE pillar) -- no
business_type restriction, per the user's explicit clarification."""
from datetime import date

DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # subscribed to "complete" -> has MANAGE pillar


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_daily_pdf_returns_pdf_for_paid_appointments(client):
    headers = _login(client, SUNRISE_EMAIL)
    today = date.today().isoformat()

    created = client.post("/api/appointments", headers=headers, json={
        "patientName": "PDF Test Patient",
        "doctorName": "Dr. Test",
        "appointmentDate": today,
        "appointmentTime": "09:00",
        "revenueAmount": 600,
    })
    assert created.status_code == 201, created.text
    appointment_id = created.json()["appointment"]["id"]

    patched = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"paymentStatus": "paid"})
    assert patched.status_code == 200, patched.text

    resp = client.get("/api/appointments/daily-pdf", headers=headers, params={"date": today})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


def test_daily_pdf_rejects_bad_date_format(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.get("/api/appointments/daily-pdf", headers=headers, params={"date": "24-07-2026"})
    assert resp.status_code == 400, resp.text

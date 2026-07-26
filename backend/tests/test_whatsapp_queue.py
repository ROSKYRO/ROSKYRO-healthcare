"""Tests for the centralized WhatsApp send queue (app/utils/
whatsapp_sender.py + routers/whatsapp.py's /queue endpoints) -- the free,
no-API-contract replacement for immediately marking every patient message
"sent". Every patient-facing message (automatic referral-lifecycle
messages AND a business's own manual /whatsapp/send) should land in
whatsapp_messages with status "queued" plus a ready-to-open wa.me link,
visible platform-wide (not scoped to any one business) only to ROSKYRO
internal via GET /queue, and only flips to "sent" once an internal user
explicitly dispatches it."""
DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # business_type: clinic, has patient_phone-bearing referrals


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _first_partner_id(client, headers):
    resp = client.get("/api/partners", headers=headers)
    assert resp.status_code == 200, resp.text
    partners = resp.json()["partners"]
    assert partners, "expected at least one seeded partner"
    return partners[0]["id"]


def test_referral_creation_queues_patient_message_not_sent(client):
    headers = _login(client, SUNRISE_EMAIL)
    partner_id = _first_partner_id(client, headers)

    resp = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id,
        "patientName": "Queue Test Patient",
        "serviceRequested": "General Consultation",
        "patientPhone": "9812345678",
    })
    assert resp.status_code == 201, resp.text
    referral_id = resp.json()["referral"]["id"]

    detail = client.get(f"/api/referrals/{referral_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    notifications = detail.json()["patient_notifications"]
    assert len(notifications) == 1
    assert notifications[0]["status"] == "queued"
    assert notifications[0]["wa_link"].startswith("https://wa.me/919812345678?text=")
    assert notifications[0]["dispatched_at"] is None


def test_manual_send_also_queues_not_sent(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.post("/api/whatsapp/send", headers=headers, json={
        "patientName": "Manual Queue Patient",
        "patientPhone": "9800011122",
        "message": "Test manual message",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["message"]["status"] == "queued"
    assert resp.json()["message"]["wa_link"]


def test_queue_is_internal_only(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.get("/api/whatsapp/queue", headers=headers)
    assert resp.status_code == 403


def test_admin_can_view_and_dispatch_queue(client, admin_headers):
    headers = _login(client, SUNRISE_EMAIL)
    partner_id = _first_partner_id(client, headers)
    referral = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id,
        "patientName": "Dispatch Test Patient",
        "serviceRequested": "General Consultation",
        "patientPhone": "9877766554",
    })
    assert referral.status_code == 201, referral.text

    queue = client.get("/api/whatsapp/queue", headers=admin_headers)
    assert queue.status_code == 200, queue.text
    items = queue.json()["queue"]
    assert items, "expected at least the just-created message in the shared queue"
    target = next(m for m in items if m["patient_name"] == "Dispatch Test Patient")
    assert target["status"] == "queued"
    assert target["org_name"] == "Sunrise Family Clinic"

    dispatched = client.post(f"/api/whatsapp/queue/{target['id']}/dispatch", headers=admin_headers)
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["message"]["status"] == "sent"
    assert dispatched.json()["message"]["dispatched_at"] is not None

    # Dispatched again -> rejected, and it should have dropped out of the
    # still-queued view.
    again = client.post(f"/api/whatsapp/queue/{target['id']}/dispatch", headers=admin_headers)
    assert again.status_code == 400

    refreshed_queue = client.get("/api/whatsapp/queue", headers=admin_headers)
    ids_still_queued = [m["id"] for m in refreshed_queue.json()["queue"]]
    assert target["id"] not in ids_still_queued

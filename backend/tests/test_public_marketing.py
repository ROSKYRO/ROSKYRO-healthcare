def test_contact_lead_requires_name(client):
    resp = client.post("/api/public/contact", json={"phone": "9800000000"})
    assert resp.status_code == 400


def test_contact_lead_requires_phone_or_email(client):
    resp = client.post("/api/public/contact", json={"name": "No Contact Info"})
    assert resp.status_code == 400


def test_contact_lead_success(client):
    resp = client.post("/api/public/contact", json={
        "name": "Pytest Visitor", "phone": "9800000099", "reason": "demo",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["lead"]["name"] == "Pytest Visitor"


def test_newsletter_subscribe_rejects_invalid_email(client):
    resp = client.post("/api/public/newsletter-subscribe", json={"email": "not-an-email"})
    assert resp.status_code == 400


def test_newsletter_subscribe_is_deduped(client, unique_suffix):
    email = f"newsletter{unique_suffix}@pytest.roskyro.example"
    first = client.post("/api/public/newsletter-subscribe", json={"email": email})
    assert first.status_code == 201
    assert first.json()["alreadySubscribed"] is False

    second = client.post("/api/public/newsletter-subscribe", json={"email": email})
    assert second.status_code == 201
    assert second.json()["alreadySubscribed"] is True

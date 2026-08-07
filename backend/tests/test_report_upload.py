"""Verification for the new report-upload feature (routers/referrals.py's
POST /referrals/{id}/report + app/utils/report_storage.py). B2 itself
isn't reachable from a sandboxed test run, so report_storage's actual
boto3 calls are monkeypatched to a fake in-memory store -- this still
exercises every real code path around it: auth, the in_progress ->
report_uploaded transition, the follow-up task, the patient WhatsApp
message (and that it actually contains a download link now), and the
report_download_url surfaced back on GET /referrals/{id}."""
import pytest
from app.utils import report_storage

DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"

_FAKE_STORE = {}


def _fake_upload_report(*, referral_id, filename, content, content_type):
    key = f"referrals/{referral_id}/fake-{len(_FAKE_STORE)}.pdf"
    _FAKE_STORE[key] = content
    return key


def _fake_build_download_link(object_key, valid_seconds=None):
    assert object_key in _FAKE_STORE
    return f"https://fake-b2.example.com/{object_key}?Authorization=faketoken"


@pytest.fixture(autouse=True)
def _patch_b2(monkeypatch):
    monkeypatch.setattr(report_storage, "is_configured", lambda: True)
    monkeypatch.setattr(report_storage, "upload_report", _fake_upload_report)
    monkeypatch.setattr(report_storage, "build_download_link", _fake_build_download_link)
    yield


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _first_partner_id(client, headers):
    resp = client.get("/api/partners", headers=headers)
    return resp.json()["partners"][0]["id"]


def _make_in_progress_referral(client, headers, admin_headers, partner_id, patient_phone="9822233344"):
    r = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id, "patientName": "Report Upload Patient",
        "serviceRequested": "MRI Scan", "patientPhone": patient_phone,
    })
    assert r.status_code == 201, r.text
    rid = r.json()["referral"]["id"]
    for status in ["accepted", "in_progress"]:
        resp = client.post(f"/api/referrals/{rid}/transition", headers=admin_headers, json={"status": status})
        assert resp.status_code == 200, resp.text
    return rid


def test_partner_uploads_report_and_patient_gets_a_real_link(client, admin_headers):
    headers = _login(client, SUNRISE_EMAIL)
    partner_id = _first_partner_id(client, headers)
    rid = _make_in_progress_referral(client, headers, admin_headers, partner_id)

    files = {"file": ("scan-report.pdf", b"%PDF-1.4 fake report bytes", "application/pdf")}
    resp = client.post(f"/api/referrals/{rid}/report", headers=admin_headers, files=files)
    assert resp.status_code == 200, resp.text
    body = resp.json()["referral"]
    assert body["status"] == "report_uploaded"
    assert body["report_file_key"] in _FAKE_STORE
    assert body["report_download_url"].startswith("https://fake-b2.example.com/")

    detail = client.get(f"/api/referrals/{rid}", headers=headers)
    assert detail.status_code == 200, detail.text
    d = detail.json()
    assert d["referral"]["report_download_url"].startswith("https://fake-b2.example.com/")

    notifications = d["patient_notifications"]
    report_msgs = [n for n in notifications if n["template_name"] == "referral_report_uploaded"]
    assert len(report_msgs) == 1, notifications
    assert "download karein" in report_msgs[0]["message"]
    assert "https://fake-b2.example.com/" in report_msgs[0]["message"]

    followups = d["followups"]
    assert any(f["note"].startswith("Review report") for f in followups)


def test_rejects_wrong_file_type(client, admin_headers):
    headers = _login(client, SUNRISE_EMAIL)
    partner_id = _first_partner_id(client, headers)
    rid = _make_in_progress_referral(client, headers, admin_headers, partner_id, patient_phone="9800011223")

    files = {"file": ("virus.exe", b"not a report", "application/x-msdownload")}
    resp = client.post(f"/api/referrals/{rid}/report", headers=admin_headers, files=files)
    assert resp.status_code == 400, resp.text


def test_rejects_upload_when_not_in_progress(client, admin_headers):
    headers = _login(client, SUNRISE_EMAIL)
    partner_id = _first_partner_id(client, headers)
    r = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id, "patientName": "Wrong State Patient",
        "serviceRequested": "General Consultation", "patientPhone": "9877011223",
    })
    rid = r.json()["referral"]["id"]  # still "sent", not "in_progress"

    files = {"file": ("report.pdf", b"%PDF-1.4", "application/pdf")}
    resp = client.post(f"/api/referrals/{rid}/report", headers=admin_headers, files=files)
    assert resp.status_code == 400, resp.text


def test_random_business_user_cannot_upload_report(client, admin_headers):
    """Only the receiving partner (or internal) can upload -- the
    referring business itself should not be able to, same authorization
    boundary as the old partner-only report_uploaded transition."""
    headers = _login(client, SUNRISE_EMAIL)
    partner_id = _first_partner_id(client, headers)
    rid = _make_in_progress_referral(client, headers, admin_headers, partner_id, patient_phone="9811100221")

    files = {"file": ("report.pdf", b"%PDF-1.4", "application/pdf")}
    resp = client.post(f"/api/referrals/{rid}/report", headers=headers, files=files)  # referring business, not partner
    assert resp.status_code == 403, resp.text

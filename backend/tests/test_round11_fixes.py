"""Regression tests for round 11's fixes:

1. settings.py's PATCH /api/settings/payment collapsed "paymentNote
   omitted from the request" and "paymentNote sent as an empty string"
   into the same `None`, and only ever wrote that `None` to storage on
   first-ever creation of the row. So once a payment note existed, a
   ROSKYRO admin trying to CLEAR it by submitting an empty paymentNote
   silently no-opped -- 200 response, no error, but the old note stayed
   forever. Fixed by distinguishing "key not sent" from "key sent empty".

2. tasks.py's PATCH /api/tasks/{task_id} accepted any string for `status`
   with zero validation -- a typo like "donee" would save silently and
   then never be counted as complete anywhere (dashboard.py's overdue
   counters and this file's own tasks_summary/list_tasks sorting all key
   off `status == "done"` specifically). Fixed by validating against the
   actual reachable status vocabulary: "open" (create_task's default),
   "in_progress" (Tasks.jsx's claim()), "done" (complete()).
"""
import pytest

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# ---------------------------------------------------------------------------
# settings.py -- patch_payment_settings()
# ---------------------------------------------------------------------------

def test_patch_payment_settings_can_clear_existing_note(client):
    headers = _login(client, ADMIN_EMAIL)

    # First, set a real note.
    resp = client.patch("/api/settings/payment", headers=headers, json={"upiId": "roskyro@upi", "paymentNote": "Pay within 48 hours"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_note"] == "Pay within 48 hours"

    # Now clear it by sending an empty string -- this must actually clear,
    # not silently keep the old note (the pre-fix bug).
    resp = client.patch("/api/settings/payment", headers=headers, json={"upiId": "roskyro@upi", "paymentNote": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_note"] is None

    # Restore for other tests/usage sharing this DB.
    client.patch("/api/settings/payment", headers=headers, json={"upiId": "roskyro@upi", "paymentNote": None})


def test_patch_payment_settings_omitting_note_leaves_it_untouched(client):
    """Distinguishing 'not sent' from 'sent empty' means omitting the key
    entirely (e.g. an admin only updating the UPI ID) must NOT wipe an
    existing note as a side effect."""
    headers = _login(client, ADMIN_EMAIL)

    resp = client.patch("/api/settings/payment", headers=headers, json={"upiId": "roskyro@upi", "paymentNote": "Keep this note"})
    assert resp.status_code == 200, resp.text

    resp = client.patch("/api/settings/payment", headers=headers, json={"upiId": "roskyro@upi"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_note"] == "Keep this note"

    client.patch("/api/settings/payment", headers=headers, json={"upiId": "roskyro@upi", "paymentNote": None})


# ---------------------------------------------------------------------------
# tasks.py -- patch_task()
# ---------------------------------------------------------------------------

def _create_task(client, headers, **overrides):
    body = {"title": "Verify GBP listing", "taskType": "gbp_setup"}
    body.update(overrides)
    resp = client.post("/api/tasks", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["task"]["id"]


def test_patch_task_rejects_invalid_status(client):
    headers = _login(client, ADMIN_EMAIL)
    task_id = _create_task(client, headers)
    resp = client.patch(f"/api/tasks/{task_id}", headers=headers, json={"status": "donee"})
    assert resp.status_code == 400, resp.text
    assert "status" in resp.json()["error"].lower()


def test_patch_task_accepts_in_progress_and_done(client):
    """The two reachable, legitimate statuses the frontend actually
    sends (Tasks.jsx's claim() -> in_progress, complete() -> done) must
    still work after adding the validation."""
    headers = _login(client, ADMIN_EMAIL)
    task_id = _create_task(client, headers)

    resp = client.patch(f"/api/tasks/{task_id}", headers=headers, json={"assignedTo": None, "status": "in_progress"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["task"]["status"] == "in_progress"

    resp = client.patch(f"/api/tasks/{task_id}", headers=headers, json={"status": "done"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["task"]["status"] == "done"
    assert resp.json()["task"]["completed_at"] is not None


def test_new_task_default_status_is_filterable(client):
    """A newly created task's default status ("open") must be one of the
    values GET /api/tasks?status= can actually filter by -- this is the
    other half of round 11's tasks.py/Tasks.jsx fix (the frontend's status
    dropdown previously offered "pending" instead of "open", so a fresh
    task was invisible under any status filter a user would try)."""
    headers = _login(client, ADMIN_EMAIL)
    task_id = _create_task(client, headers, title="Round 11 filter check task")

    resp = client.get("/api/tasks", headers=headers, params={"status": "open"})
    assert resp.status_code == 200, resp.text
    ids = [t["id"] for t in resp.json()["tasks"]]
    assert task_id in ids

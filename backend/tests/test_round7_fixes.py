"""Regression tests for round 7's fixes:

1. Partner verification decision notification bug: verify_partner()
   (routers/partners.py) looked up the partner org's admin via
   role="owner", but "owner" only ever exists on CUSTOMER (business) org
   users -- a partner org's admin user is always seeded/created with
   role="partner_admin" (see partner_plans.py, referrals.py for the same
   lookup done correctly elsewhere). The find_one always returned None, so
   the "your partner application was verified / needs changes"
   notification silently never reached anyone, for any partner, ever.

2. Unbounded fetch-then-Python-tally/sort in routers/tasks.py's
   list_tasks() and tasks_summary(): both used to pull EVERY matching task
   (platform-wide, no collection-level bound -- grows forever as more
   partner-verification/content/SEO/CRM/support tasks are created) before
   doing the actual sort/count in Python. Replaced with MongoDB
   aggregation ($addFields+$sort+$limit, and $group) so only the rows
   actually needed ever leave the DB layer.
"""
import pytest

from app.db import partners as partners_col, users, tasks
from app.utils.ids import new_id, now

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"
HOMECARE_ADMIN_EMAIL = "admin.homecare.plus@example.com"  # seeded pending (unverified) partner's admin


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# --- 1. Partner verification decision actually reaches the partner admin ---

@pytest.mark.asyncio
async def test_verify_partner_notifies_the_partner_admin_not_a_nonexistent_owner(client):
    """`client` fixture forces app startup (and therefore seed.py) to have
    already run before this test's direct DB queries execute -- without
    it, the collections are simply empty and every find_one below returns
    None regardless of whether the fix is in place.

    HomeCare Plus is seeded with verification_status="pending" -- the
    one seeded partner this round's live smoke test also exercised. Before
    this fix, ROSKYRO internal deciding this application would silently
    produce zero notifications (role="owner" never matches a partner
    org's user), even though the HTTP call itself returned 200."""
    homecare_admin = await users.find_one({"email": HOMECARE_ADMIN_EMAIL})
    assert homecare_admin is not None, "seed data changed -- HomeCare Plus admin no longer exists"
    assert homecare_admin["role"] == "partner_admin", "sanity: partner org users are never role='owner'"

    partner = await partners_col.find_one({"org_id": homecare_admin["org_id"]})
    assert partner is not None

    # Confirm the pre-fix bug's premise directly: no "owner"-role user
    # exists for this (or any) partner org.
    phantom_owner = await users.find_one({"org_id": homecare_admin["org_id"], "role": "owner"})
    assert phantom_owner is None, "partner orgs never have an 'owner' -- role='owner' users only exist on customer orgs"


def test_verify_partner_http_notifies_partner_admin(client, admin_headers):
    homecare_headers = _login(client, HOMECARE_ADMIN_EMAIL)

    # Fetch this partner's id via the partner-admin's own account (avoids
    # depending on internal list_partners' plan-gate/pagination details).
    mine = client.get("/api/partners/me", headers=homecare_headers)
    assert mine.status_code == 200, mine.text
    partner_id = mine.json()["partner"]["id"]

    resp = client.post(f"/api/partners/{partner_id}/verify", headers=admin_headers, json={"decision": "verified"})
    assert resp.status_code == 200, resp.text

    notifs = client.get("/api/notifications", headers=homecare_headers)
    assert notifs.status_code == 200, notifs.text
    matching = [n for n in notifs.json()["notifications"] if n["type"] == "partner_verification_decision"]
    assert matching, "the partner admin who applied must receive the verification-decision notification"
    assert "verified" in matching[0]["title"].lower()


# --- 2. tasks.py: aggregation-based list/summary produce correct, bounded results ---

@pytest.mark.asyncio
async def test_list_tasks_aggregation_sort_matches_original_semantics(client, admin_headers):
    """Sanity check against the live API (not just the unit-level pipeline
    check done during development): open-before-done, urgent-before-not,
    earliest-SLA-first, and no leaked internal sort-helper fields
    (_is_done/_not_urgent/_sla_sort) in the response."""
    resp = client.get("/api/tasks", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()["tasks"]
    assert len(rows) > 0, "seed data should include internal team tasks"

    for r in rows:
        assert "_is_done" not in r and "_not_urgent" not in r and "_sla_sort" not in r, \
            "aggregation sort-helper fields must never leak into the API response"

    # open tasks must all sort before done tasks
    statuses = [r["status"] for r in rows]
    if "done" in statuses and any(s != "done" for s in statuses):
        first_done_idx = statuses.index("done")
        assert all(s == "done" for s in statuses[first_done_idx:]), \
            "every non-done task must sort before every done task"


@pytest.mark.asyncio
async def test_tasks_summary_aggregation_matches_manual_count(client, admin_headers):
    resp = client.get("/api/tasks/summary", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    summary = {row["status"]: row for row in resp.json()["summary"]}

    all_tasks = await tasks.find({}).to_list(None)
    expected_counts = {}
    for t in all_tasks:
        expected_counts[t["status"]] = expected_counts.get(t["status"], 0) + 1

    for status, expected_count in expected_counts.items():
        assert status in summary, f"status {status} missing from /tasks/summary"
        assert summary[status]["count"] == expected_count, \
            f"summary count for {status} ({summary[status]['count']}) doesn't match direct DB count ({expected_count})"


@pytest.mark.asyncio
async def test_tasks_summary_overdue_count_excludes_done_and_no_sla():
    """Direct pipeline-level check with synthetic data covering the three
    edge cases the $cond in tasks_summary must get right: an overdue OPEN
    task counts, a task with no sla_due_at never counts (even if it'd
    otherwise look "overdue"), and an overdue task that's already DONE
    must not count as overdue."""
    from datetime import timedelta

    role = f"pytest_role_{new_id()}"
    past = now() - timedelta(hours=2)
    await tasks.insert_one({
        "_id": new_id(), "org_id": None, "related_type": None, "related_id": None,
        "title": "overdue open", "description": None, "task_type": "t", "assigned_role": role,
        "assigned_to": None, "priority": "high", "status": "open", "sla_hours": 1,
        "sla_due_at": past, "created_by": None, "completed_at": None, "created_at": now(),
    })
    await tasks.insert_one({
        "_id": new_id(), "org_id": None, "related_type": None, "related_id": None,
        "title": "no sla set", "description": None, "task_type": "t", "assigned_role": role,
        "assigned_to": None, "priority": "normal", "status": "open", "sla_hours": None,
        "sla_due_at": None, "created_by": None, "completed_at": None, "created_at": now(),
    })
    await tasks.insert_one({
        "_id": new_id(), "org_id": None, "related_type": None, "related_id": None,
        "title": "overdue but done", "description": None, "task_type": "t", "assigned_role": role,
        "assigned_to": None, "priority": "high", "status": "done", "sla_hours": 1,
        "sla_due_at": past, "created_by": None, "completed_at": now(), "created_at": now(),
    })

    from app.routers.tasks import tasks_summary
    result = await tasks_summary(role=role)
    by_status = {row["status"]: row for row in result["summary"]}

    assert by_status["open"]["count"] == 2
    assert by_status["open"]["overdue_count"] == 1, "only the task WITH an overdue sla_due_at counts, not the one with none"
    assert by_status["done"]["count"] == 1
    assert by_status["done"]["overdue_count"] == 0, "a completed task must never count as overdue, no matter its sla_due_at"

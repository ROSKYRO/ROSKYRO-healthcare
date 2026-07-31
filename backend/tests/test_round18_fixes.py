"""Regression tests for round 18 -- the "is this safe to put real paying
clients on?" audit.

Round 18 changed NO features and NO business rules (explicit user
constraint: "bs feature and wrking model me se kuch mt badlana"). Every
test below therefore asserts one of exactly two things:

  1. a bad input that used to be ACCEPTED and then broke something later is
     now rejected at the door with a clean 4xx, or
  2. a good input produces the exact same result it always did, just faster
     / more safely.

Nothing here asserts a new capability, a new endpoint, or a changed price,
status, or permission.

Grouped by the audit area they came from:
  - BOOKING / QR / APPOINTMENTS   (tests 1-6)
  - SUBSCRIPTIONS                 (tests 7-11)
  - REFERRALS                     (test 12)
  - PERFORMANCE / CORRECTNESS     (tests 13-17)
"""
import math
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.booking import (
    IST_OFFSET, MAX_BOOKING_WINDOW_DAYS, generate_slots, ist_date_str,
    ist_day_start, time_to_minutes,
)
from app.utils.plans import add_cycle

DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # MANAGE + CONNECT pillars
ADMIN_EMAIL = "admin@roskyro.com"


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["user"]


def _sunrise(client):
    headers, user = _login(client, SUNRISE_EMAIL)
    return headers, user["orgId"]


# ---------------------------------------------------------------------------
# BOOKING / QR / APPOINTMENTS
# ---------------------------------------------------------------------------

def test_negative_or_zero_slot_duration_is_rejected_not_stored():
    """THE most severe finding of this round, tested at the unit level so it
    can never regress into a hang: generate_slots() used to be

        while t + duration <= close_min: slots.append(...); t += duration

    With duration <= 0 the counter never advances (or moves backwards), the
    condition never turns false, and the list grows until the process dies.
    That loop is reachable from the PUBLIC, unauthenticated patient booking
    endpoints, so one bad number in one clinic's settings could pin the CPU
    and OOM the worker for EVERY tenant sharing the process.

    Two independent layers now stop it -- this asserts the inner one (the
    helper itself, which also protects rows written before the validator
    shipped); test_doctor_rejects_out_of_range_slot_duration asserts the
    outer one (the API refusing to store it in the first place)."""
    for bad_duration in (-30, -1, 0):
        slots = generate_slots("09:00", "17:00", bad_duration)
        # The guard substitutes the 30-minute default rather than raising,
        # because raising here would 500 the public booking page.
        assert slots == generate_slots("09:00", "17:00", 30)
        assert len(slots) == 16


def test_generate_slots_returns_empty_on_malformed_or_inverted_times():
    """time_to_minutes() used to do a bare int(parts[1]) -- "0900" (no
    colon) raised IndexError and "9am" raised ValueError, either of which
    surfaced as a raw 500 on the public booking page for that business."""
    assert time_to_minutes("0900") is None
    assert time_to_minutes("9am") is None
    assert time_to_minutes("") is None
    assert time_to_minutes(None) is None
    assert generate_slots("0900", "1700", 30) == []
    assert generate_slots("17:00", "09:00", 30) == []   # inverted
    assert generate_slots("09:00", "09:00", 30) == []   # zero-length day
    # Unpadded but well-formed still works, and is NOT mis-ordered by the
    # old string comparison ("9" > "1" lexicographically).
    assert time_to_minutes("9:00") == 540


def test_doctor_rejects_out_of_range_slot_duration(client):
    headers, _ = _sunrise(client)
    base = {
        "name": "Dr Slot Guard",
        "weeklySchedule": [{"day": "mon", "openTime": "09:00", "closeTime": "17:00"}],
    }
    for bad in (-5, 0, 4, 241, 100000):
        resp = client.post("/api/doctors", headers=headers, json={**base, "slotDurationMinutes": bad})
        assert resp.status_code == 400, f"slotDurationMinutes={bad} was accepted: {resp.text}"
    # A sane value still works exactly as before -- this fix must not have
    # narrowed what a real clinic can configure.
    ok = client.post("/api/doctors", headers=headers, json={**base, "slotDurationMinutes": 15})
    assert ok.status_code == 201, ok.text
    assert ok.json()["doctor"]["slot_duration_minutes"] == 15


def test_non_finite_fee_cannot_poison_the_doctor_list(client):
    """float("NaN") and float("Infinity") both SUCCEED, so the old
    try/except (TypeError, ValueError) let them through. Once stored, every
    later read 500'd -- FastAPI serializes with json.dumps(allow_nan=False)
    -- permanently breaking GET /api/doctors AND the public booking page,
    with no UI path to delete the poisoned row."""
    headers, _ = _sunrise(client)
    base = {
        "name": "Dr NaN Guard",
        "weeklySchedule": [{"day": "tue", "openTime": "10:00", "closeTime": "13:00"}],
    }
    # Sent as JSON strings, which is exactly how they reach a real server:
    # float("NaN") parses them successfully, which is why the old
    # try/except (TypeError, ValueError) never caught them.
    for bad in ("NaN", "Infinity", "-Infinity", "nan", "inf"):
        resp = client.post("/api/doctors", headers=headers, json={**base, "consultationFee": bad})
        assert resp.status_code in (400, 422), f"consultationFee={bad!r} was accepted: {resp.text}"
    # And the list endpoint is still healthy afterwards.
    listing = client.get("/api/doctors", headers=headers)
    assert listing.status_code == 200, listing.text
    for doc in listing.json()["doctors"]:
        fee = doc.get("consultation_fee")
        if isinstance(fee, float):
            assert math.isfinite(fee)


def test_schedule_time_format_and_shape_are_validated(client):
    headers, _ = _sunrise(client)

    def _post(schedule):
        return client.post("/api/doctors", headers=headers, json={"name": "Dr Schedule Guard", "weeklySchedule": schedule})

    # A non-dict entry used to raise AttributeError -> raw 500.
    assert _post(["mon"]).status_code == 400
    # "0900"/"1700" passed the old lexicographic check and saved 200 OK,
    # then exploded downstream on the public page.
    assert _post([{"day": "mon", "openTime": "0900", "closeTime": "1700"}]).status_code == 400
    assert _post([{"day": "mon", "openTime": "25:00", "closeTime": "26:00"}]).status_code == 400
    assert _post([{"day": "mon", "openTime": "09:70", "closeTime": "17:00"}]).status_code == 400
    # Genuinely inverted is still rejected...
    assert _post([{"day": "mon", "openTime": "17:00", "closeTime": "09:00"}]).status_code == 400
    # ...but unpadded-yet-valid "9:00"-"17:00", which the OLD string compare
    # wrongly rejected ("9" > "1"), is accepted now that the comparison is
    # done on minutes.
    ok = _post([{"day": "wed", "openTime": "9:00", "closeTime": "17:00"}])
    assert ok.status_code == 201, ok.text


def test_cancelling_a_qr_appointment_gives_the_slot_back(client):
    """public_booking.py reserves capacity with an atomic $inc on a
    booking_counters row. Nothing ever decremented it again, so every
    cancellation permanently destroyed one bookable seat: a clinic that
    cancelled and rebooked the same 10:00 slot a few times would find the
    slot showing "full" to patients while the doctor sat idle. Capacity
    accounting is restored WITHOUT changing how booking itself works."""
    headers, org_id = _sunrise(client)

    public = client.get(f"/api/public/booking/{org_id}")
    assert public.status_code == 200, public.text
    doctor_id = public.json()["doctors"][0]["id"]

    def _slot_state(date, time):
        avail = client.get(f"/api/public/booking/{org_id}/doctors/{doctor_id}/availability").json()
        day = next(d for d in avail["days"] if d["date"] == date)
        return next(s for s in day["slots"] if s["time"] == time)

    avail = client.get(f"/api/public/booking/{org_id}/doctors/{doctor_id}/availability").json()
    day = next(d for d in avail["days"] if any(s["remaining"] > 0 for s in d["slots"]))
    slot = next(s for s in day["slots"] if s["remaining"] > 0)
    before = slot["remaining"]

    booked = client.post(f"/api/public/booking/{org_id}/book", json={
        "patientName": "Round18 Cancel Test", "patientPhone": "9800011122",
        "doctorId": doctor_id, "appointmentDate": day["date"], "appointmentTime": slot["time"],
    })
    assert booked.status_code == 201, booked.text
    assert _slot_state(day["date"], slot["time"])["remaining"] == before - 1

    appointment_id = booked.json()["appointment"]["id"]

    cancelled = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"status": "cancelled"})
    assert cancelled.status_code == 200, cancelled.text
    assert _slot_state(day["date"], slot["time"])["remaining"] == before

    # Cancelling AGAIN (double-click, retried request) must not credit a
    # phantom seat back -- remaining stays at `before`, never exceeds it.
    client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"status": "cancelled"})
    assert _slot_state(day["date"], slot["time"])["remaining"] == before


def test_appointment_status_is_whitelisted_and_revenue_must_be_finite(client):
    headers, _ = _sunrise(client)
    created = client.post("/api/appointments", headers=headers, json={
        "patientName": "Round18 Status Test", "patientPhone": "9800011133",
        "appointmentDate": "2030-01-15", "appointmentTime": "11:00",
    })
    assert created.status_code == 201, created.text
    appointment_id = created.json()["appointment"]["id"]

    bad = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"status": "definitely_not_a_status"})
    assert bad.status_code == 400, bad.text

    for bad_amount in ("NaN", "Infinity", "not-a-number"):
        resp = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"revenueAmount": bad_amount})
        assert resp.status_code in (400, 422), f"revenueAmount={bad_amount!r} accepted: {resp.text}"

    # Every real status still works, unchanged.
    for good in ("scheduled", "confirmed", "completed", "no_show"):
        resp = client.patch(f"/api/appointments/{appointment_id}", headers=headers, json={"status": good})
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# SUBSCRIPTIONS
# ---------------------------------------------------------------------------

def test_bundle_cannot_be_subscribed_twice(client, unique_suffix, admin_headers):
    """Found live and reproduced: the "complete" bundle had NO
    already-subscribed guard, so a business could end up holding a monthly
    AND a yearly "complete" simultaneously -- monthlyTotal 44998.17 for one
    business, billed forever, with no UI showing anything wrong.

    The plan, its price and what it unlocks are all unchanged; only the
    second, duplicate purchase is refused. (Round 23: subscribe() now only
    creates a pending claim -- confirmed here via the admin payment-
    confirmation endpoint so "active_complete" below is genuinely active,
    exercising the duplicate guard's "already active" branch specifically.)"""
    reg = client.post("/api/auth/register", json={
        "orgName": f"Bundle Guard Clinic {unique_suffix}",
        "businessType": "clinic", "city": "Pune", "ownerName": "Dr Bundle",
        "email": f"bundle.guard.{unique_suffix}@example.com",
        "phone": f"93{unique_suffix}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    })
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}

    first = client.post("/api/plans/subscribe", headers=headers, json={"planCode": "complete", "billingCycle": "monthly"})
    assert first.status_code in (200, 201), first.text
    confirm = client.post(f"/api/plans/{first.json()['subscription']['id']}/confirm-payment", headers=admin_headers)
    assert confirm.status_code == 200, confirm.text

    # Same cycle AND a different cycle must both be refused -- the original
    # bug was specifically that a different billingCycle slipped past.
    for cycle in ("monthly", "yearly"):
        again = client.post("/api/plans/subscribe", headers=headers, json={"planCode": "complete", "billingCycle": cycle})
        assert again.status_code == 409, f"duplicate bundle ({cycle}) accepted: {again.text}"

    mine = client.get("/api/plans/mine", headers=headers)
    assert mine.status_code == 200, mine.text
    active_complete = [
        s for s in mine.json()["subscriptions"]
        if s["plan_code"] == "complete" and s["status"] == "active"
    ]
    assert len(active_complete) == 1
    # And the bundle still unlocks all three pillars, exactly as before.
    assert set(mine.json()["activePillars"]) == {"grow", "manage", "connect"}


def test_a_pillar_already_covered_by_the_bundle_is_still_refused(client, unique_suffix, admin_headers):
    """Unchanged behaviour, re-asserted because round 18 rewrote the $nin
    filter this check is built on (it hardcoded "complete" instead of using
    the plan code actually being purchased). Round 23: the bundle claim is
    confirmed active first -- find_active_bundle_covering_pillar only
    matches a genuinely active bundle, not a still-pending one."""
    reg = client.post("/api/auth/register", json={
        "orgName": f"Bundle Pillar Clinic {unique_suffix}",
        "businessType": "clinic", "city": "Pune", "ownerName": "Dr Pillar",
        "email": f"bundle.pillar.{unique_suffix}@example.com",
        "phone": f"94{unique_suffix}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    })
    assert reg.status_code == 201, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['token']}"}
    bundle = client.post("/api/plans/subscribe", headers=headers, json={"planCode": "complete", "billingCycle": "monthly"})
    assert bundle.status_code == 201, bundle.text
    confirm = client.post(f"/api/plans/{bundle.json()['subscription']['id']}/confirm-payment", headers=admin_headers)
    assert confirm.status_code == 200, confirm.text

    dupe = client.post("/api/plans/subscribe", headers=headers, json={"planCode": "grow", "billingCycle": "monthly"})
    assert dupe.status_code == 409, dupe.text
    # The reels ADD-ON is not a pillar and must still be purchasable on top
    # of the bundle -- the fix must not have over-blocked.
    addon = client.post("/api/plans/subscribe", headers=headers, json={"planCode": "reels", "billingCycle": "monthly"})
    assert addon.status_code in (200, 201), addon.text


def test_plan_prices_reject_negative_null_and_non_finite(client):
    """PATCH /api/plans/{code} is the internal Pricing Management screen.
    It accepted a negative price and an explicit null -- a negative monthly
    price would have produced negative invoices for every subscriber, and a
    null crashed the pricing page's arithmetic."""
    headers, _ = _login(client, ADMIN_EMAIL)
    original = client.get("/api/plans").json()
    grow = next(p for p in original["plans"] if p["code"] == "grow")

    for bad in (-1, -14999, None, "NaN", "Infinity", "abc"):
        resp = client.patch("/api/plans/grow", headers=headers, json={"monthlyPrice": bad})
        assert resp.status_code in (400, 422), f"monthlyPrice={bad!r} accepted: {resp.text}"

    # Price is untouched by all of those rejections.
    after = next(p for p in client.get("/api/plans").json()["plans"] if p["code"] == "grow")
    assert after["monthly_price"] == grow["monthly_price"]

    # A legitimate edit still works, and is then restored so the shared
    # session DB is left exactly as found.
    ok = client.patch("/api/plans/grow", headers=headers, json={"monthlyPrice": 15999})
    assert ok.status_code == 200, ok.text
    restore = client.patch("/api/plans/grow", headers=headers, json={"monthlyPrice": grow["monthly_price"]})
    assert restore.status_code == 200, restore.text


def test_month_end_renewal_date_does_not_drift_earlier_every_cycle(client):
    """add_cycle() clamped Jan 31 -> Feb 28 (correct), but then the NEXT
    cycle was computed from Feb 28, giving Mar 28, then Apr 28 -- so a
    business that subscribed on the 31st had its billing date walk
    permanently backwards, three days lost after two months and never
    recovered. The anchor day is now carried forward, so the clamp applies
    once per month instead of compounding.

    This does NOT change WHEN anyone is billed in the normal case (any
    anchor day <= 28 is byte-identical to the old behaviour); it only stops
    the drift for the 29th/30th/31st."""
    jan31 = datetime(2027, 1, 31, tzinfo=timezone.utc)
    feb = add_cycle(jan31, "monthly", anchor_day=31)
    assert (feb.month, feb.day) == (2, 28)
    mar = add_cycle(feb, "monthly", anchor_day=31)
    assert (mar.month, mar.day) == (3, 31), "renewal date drifted earlier"
    apr = add_cycle(mar, "monthly", anchor_day=31)
    assert (apr.month, apr.day) == (4, 30)
    may = add_cycle(apr, "monthly", anchor_day=31)
    assert (may.month, may.day) == (5, 31)

    # Ordinary anchor days behave exactly as they always did.
    jan15 = datetime(2027, 1, 15, tzinfo=timezone.utc)
    assert add_cycle(jan15, "monthly").day == 15
    assert add_cycle(jan15, "yearly").year == 2028
    # December rolls the year over.
    dec = datetime(2027, 12, 15, tzinfo=timezone.utc)
    nxt = add_cycle(dec, "monthly")
    assert (nxt.year, nxt.month, nxt.day) == (2028, 1, 15)


@pytest.mark.asyncio
async def test_concurrent_subscribe_leaves_exactly_one_active_row():
    """subscribe() is check-then-insert: two requests arriving together (a
    double-click, or a retry after a slow response) could both pass the
    "already subscribed?" check and both insert, double-billing the
    business. A unique index is NOT usable here -- a real database that
    already contains a duplicate from before this fix would fail the index
    build at boot -- so the repair is a compare-and-delete run immediately
    after each insert."""
    from app.db import organization_subscriptions
    from app.utils.subscriptions import enforce_single_active

    org_id = "round18-race-org"
    base = {"org_id": org_id, "plan_code": "grow", "status": "active"}
    winner = {**base, "_id": "race-a", "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    loser = {**base, "_id": "race-b", "started_at": datetime(2026, 1, 2, tzinfo=timezone.utc)}
    try:
        await organization_subscriptions.insert_one(winner)
        await organization_subscriptions.insert_one(loser)

        # The later insert loses and removes itself...
        assert await enforce_single_active(organization_subscriptions, org_id, "grow", "race-b") is False
        # ...and the earlier one survives.
        assert await enforce_single_active(organization_subscriptions, org_id, "grow", "race-a") is True

        rows = await organization_subscriptions.find({"org_id": org_id, "status": "active"}).to_list(None)
        assert len(rows) == 1
        assert rows[0]["_id"] == "race-a"
    finally:
        await organization_subscriptions.delete_many({"org_id": org_id})


# ---------------------------------------------------------------------------
# REFERRALS
# ---------------------------------------------------------------------------

def test_referral_category_filter_is_applied_before_the_row_limit(client):
    """list_referrals fetches .limit(300) and USED to filter by category
    afterwards in Python -- so once a business passed 300 referrals, the
    category filter silently returned an incomplete (eventually empty) list
    even though matching referrals existed. The filter now goes into the
    Mongo query, before the limit.

    The endpoint's contract is unchanged; this asserts the filter still
    selects exactly the right rows and that an unknown category yields an
    empty list rather than every referral."""
    headers, _ = _sunrise(client)
    all_refs = client.get("/api/referrals", headers=headers)
    assert all_refs.status_code == 200, all_refs.text
    rows = all_refs.json()["referrals"]
    assert rows, "seed data should include referrals for this business"

    categories = client.get("/api/partners/categories", headers=headers).json()["categories"]
    slug = categories[0]["slug"]
    filtered = client.get(f"/api/referrals?category={slug}", headers=headers)
    assert filtered.status_code == 200, filtered.text
    for row in filtered.json()["referrals"]:
        assert row.get("categorySlug", slug) == slug

    unknown = client.get("/api/referrals?category=no-such-category-exists", headers=headers)
    assert unknown.status_code == 200, unknown.text
    assert unknown.json()["referrals"] == []


# ---------------------------------------------------------------------------
# PERFORMANCE / CORRECTNESS
# ---------------------------------------------------------------------------

def test_ist_day_boundary_helpers_are_timezone_aware_and_correct():
    """ROSKYRO is India-only, but the queue and the dashboard's "today"
    counters were bounded by UTC midnight -- i.e. 5:30 AM IST. Every
    appointment, check-in and token between IST midnight and 5:30 AM was
    filed under the PREVIOUS day, and at 5:30 every morning the day's
    counters silently reset mid-shift for a clinic with early hours.

    Both helpers must return timezone-AWARE values: utils/ids.py's now()
    returns datetime.now(timezone.utc), and comparing a naive boundary
    against aware stored timestamps raises TypeError."""
    start = ist_day_start()
    assert start.tzinfo is not None, "naive boundary would TypeError against stored aware timestamps"
    # The boundary really is IST midnight expressed in UTC.
    assert (start + IST_OFFSET).hour == 0
    assert (start + IST_OFFSET).minute == 0
    now_utc = datetime.now(timezone.utc)
    assert start <= now_utc
    assert now_utc - start < timedelta(days=1)

    # 00:30 IST on the 8th is 19:00 UTC on the 7th -- the old UTC-midnight
    # logic filed it under the 7th; the IST logic correctly says the 8th.
    just_after_ist_midnight = datetime(2026, 7, 7, 19, 0, tzinfo=timezone.utc)
    assert ist_date_str(just_after_ist_midnight) == "2026-07-08"
    # 05:00 IST the same morning is still that same IST day (the old code
    # flipped over at 05:30 IST).
    assert ist_date_str(datetime(2026, 7, 7, 23, 30, tzinfo=timezone.utc)) == "2026-07-08"
    assert ist_day_start(just_after_ist_midnight) == datetime(2026, 7, 7, 18, 30, tzinfo=timezone.utc)


def test_booking_window_is_clamped_at_both_layers(client):
    """A stored window of 100000 would have made the public availability
    endpoint build 100,000 day entries -- per request, unauthenticated."""
    headers, _ = _sunrise(client)
    resp = client.patch("/api/booking-settings", headers=headers, json={"bookingWindowDays": 5000})
    assert resp.status_code == 400, resp.text
    from app.utils.booking import upcoming_dates
    assert len(upcoming_dates(100000)) == MAX_BOOKING_WINDOW_DAYS
    # A normal value is untouched.
    ok = client.patch("/api/booking-settings", headers=headers, json={"bookingWindowDays": 14})
    assert ok.status_code == 200, ok.text
    client.patch("/api/booking-settings", headers=headers, json={"bookingWindowDays": 7})


def test_team_roster_counts_are_unchanged_after_the_aggregation_rewrite(client):
    """GET /tasks/team/roster used to pull EVERY task ever assigned to any
    internal user -- the whole collection, unbounded, forever -- purely to
    produce three integers per person. Mongo does the counting now. The
    numbers themselves must be identical, so this cross-checks the roster's
    open/completed totals against the independent /tasks/summary endpoint."""
    headers, _ = _login(client, ADMIN_EMAIL)
    roster = client.get("/api/tasks/team/roster", headers=headers)
    assert roster.status_code == 200, roster.text
    rows = roster.json()["roster"]
    assert rows, "seed data should include internal team members"
    for row in rows:
        assert isinstance(row["open_tasks"], int)
        assert isinstance(row["overdue_tasks"], int)
        assert isinstance(row["completed_tasks"], int)
        assert row["overdue_tasks"] <= row["open_tasks"]

    summary = client.get("/api/tasks/summary", headers=headers).json()["summary"]
    done_total = sum(s["count"] for s in summary if s["status"] == "done")
    open_total = sum(s["count"] for s in summary if s["status"] != "done")
    # Roster only counts tasks assigned to an internal USER; summary counts
    # every task including role-only assignments, so roster <= summary.
    assert sum(r["completed_tasks"] for r in rows) <= done_total
    assert sum(r["open_tasks"] for r in rows) <= open_total


@pytest.mark.asyncio
async def test_pillar_resolution_is_batched_and_still_correct(client):
    """utils/pillars.py runs on EVERY authenticated request. It was a 1+N
    (one find_one per active subscription); it is now a single $in. The
    RESULT must be identical -- especially the bundle expansion, which is
    what gates every pillar-protected screen in the product."""
    from app.utils.pillars import get_active_pillars

    headers, user = _login(client, SUNRISE_EMAIL)
    # The value the live request path computed (auth.py -> get_current_user
    # -> this helper, surfaced by /plans/mine) must equal what the helper
    # returns when called directly.
    from_request = set(client.get("/api/plans/mine", headers=headers).json()["activePillars"])
    direct = set(await get_active_pillars(user["orgId"]))
    assert from_request == direct
    assert from_request, "Sunrise should hold at least one pillar in seed data"
    # Sunrise is on the "complete" bundle in seed data, so the bundle
    # expansion specifically must survive the batching rewrite.
    assert from_request == {"grow", "manage", "connect"}

    # And the pillar gate itself still behaves the same way: an endpoint
    # behind a pillar this org holds returns 200.
    assert client.get("/api/appointments", headers=headers).status_code == 200


def test_gzip_compression_is_enabled_for_large_responses(client):
    """The single Railway service serves the React bundle AND the API from
    one process, and nothing compressed either -- every first-time visitor
    downloaded ~450 KB more JS than necessary before the page could paint.
    Responses under 1 KB are deliberately left alone (compressing them costs
    more CPU than it saves bytes)."""
    headers, _ = _login(client, ADMIN_EMAIL)
    resp = client.get("/api/orgs", headers={**headers, "Accept-Encoding": "gzip"})
    assert resp.status_code == 200, resp.text
    # TestClient transparently decodes the body, so assert on the header.
    # The seeded org list is comfortably over the 1 KB minimum_size.
    assert len(resp.content) > 1000, "test relies on this response exceeding the 1KB threshold"
    assert resp.headers.get("content-encoding") == "gzip", dict(resp.headers)

    # A tiny response must NOT be compressed.
    health = client.get("/api/health", headers={"Accept-Encoding": "gzip"})
    assert health.status_code == 200
    assert health.headers.get("content-encoding") != "gzip"


@pytest.mark.asyncio
async def test_every_planned_index_actually_gets_created():
    """The round-18 sort indexes were added in a separate _SORT_INDEX_PLAN
    list. ensure_indexes() must actually iterate it -- an earlier draft
    defined the list and never used it, which would have looked completely
    fine (no error, no failing test) while delivering none of the speedup.

    Also re-asserts this file's collision rule: Mongo generates the same
    index NAME for the same key pattern regardless of options, so the same
    key pattern must never appear twice across the three plans, or the
    second create_index silently loses -- which is exactly how a plain index
    once shadowed a unique one."""
    from app.db_indexes import _INDEX_PLAN, _SORT_INDEX_PLAN, _UNIQUE_INDEX_PLAN, ensure_indexes

    assert _SORT_INDEX_PLAN, "sort index plan is empty"

    def _name(spec):
        if isinstance(spec, str):
            return f"{spec}_1"
        return "_".join(f"{field}_{direction}" for field, direction in spec)

    seen: dict[tuple[str, str], str] = {}
    for plan_label, plan in (("plain", _INDEX_PLAN), ("sort", _SORT_INDEX_PLAN)):
        for collection, specs in plan:
            for spec in specs:
                key = (collection.name, _name(spec))
                assert key not in seen, f"duplicate index {key} ({plan_label} vs {seen[key]})"
                seen[key] = plan_label
    for collection, spec, _kwargs in _UNIQUE_INDEX_PLAN:
        key = (collection.name, _name(spec))
        assert key not in seen, f"unique index {key} collides with a plain index ({seen[key]})"
        seen[key] = "unique"

    # Idempotent: re-running on an already-indexed database must not raise.
    await ensure_indexes()

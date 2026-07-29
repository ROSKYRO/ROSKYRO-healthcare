"""Regression tests for round 19 -- two specific, user-requested fixes on
top of round 18's "is this safe for real clients" pass. Per the standing
constraint from round 18 onward ("bs feature and wrking model me se kuch
mt badlana"), round 19 touches ONLY these two items, both of which the
user explicitly asked to have fixed even though they change *timing/
identity behaviour* (spelled out below), and nothing else about the
product's features or working model:

  1. PATIENT IDENTITY (tests 1-10): patients.py used to build a patient's
     whole history by matching on the `patient_name` STRING. Two patients
     sharing a name at the same clinic saw each other's appointments,
     invoices, follow-ups and WhatsApp messages. Every history-carrying
     write path now resolves a stable `patient_id` (app/utils/patients.py)
     keyed on (name, phone) together, and patients.py joins on that id,
     falling back to the old name match ONLY for rows that predate this
     change (so no business's existing history disappears the day this
     ships). A one-time, re-runnable POST /api/patients/link-history
     backfills the legacy rows.

  2. RENEWAL DUE DATE (tests 11-15): subscription_renewals.py used to
     track renewals purely by calendar month ("period": "YYYY-MM"), with
     no notion of the specific day-of-month a subscription actually
     renews on -- even though Plans & Billing (GET /api/plans/mine)
     already promises an exact anniversary date via
     app/utils/plans.py's next_renewal_date(). A generated charge now
     also carries `due_date`, computed with the exact same anchor-day
     math, so the charge and the promise always agree. This does NOT
     change WHEN ROSKYRO's admin team can generate charges (still one
     manual per-period action, can still be run ahead of the due date) --
     only what date a charge claims to be for. Existing renewal charges
     (which have no due_date) are left exactly as they are: no claw-back,
     no re-billing.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.db import (
    appointments, invoices, organization_subscriptions, organizations,
    patient_followups, patients, queue_entries, subscription_renewals,
    whatsapp_messages,
)
from app.routers.subscription_renewals import _renewal_due_date
from app.utils.ids import new_id, now
from app.utils.patients import (
    linked_history_filter, name_key, phone_key, resolve_patient_id,
)

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
# PATIENT IDENTITY -- key derivation + resolve_patient_id (pure unit tests)
# ---------------------------------------------------------------------------

def test_phone_key_only_accepts_a_real_10_digit_number():
    assert phone_key("+91-98000 00001") == phone_key("098000 00001") == phone_key("9800000001")
    assert phone_key("9800000001") == "9800000001"
    # Too short to identify anyone -- must not become a key that could
    # collide two unrelated patients who both left a partial number.
    assert phone_key("98000") is None
    assert phone_key(None) is None
    assert phone_key("") is None


def test_name_key_folds_case_and_collapses_whitespace():
    assert name_key("Ramesh   Kumar") == name_key("ramesh kumar") == "ramesh kumar"
    assert name_key("  ") is None
    assert name_key(None) is None


@pytest.mark.asyncio
async def test_same_phone_and_name_resolve_to_the_same_patient(unique_suffix):
    org_id = f"pytest-org-identity-{unique_suffix}"
    phone = f"90000{unique_suffix}"[-10:].rjust(10, "1")
    first = await resolve_patient_id(org_id, "Ramesh Kumar", phone)
    second = await resolve_patient_id(org_id, "Ramesh Kumar", phone)
    assert first is not None
    assert first == second, "the same (name, phone) must resolve to one patient, not create a duplicate"


@pytest.mark.asyncio
async def test_same_name_different_phone_are_different_patients_not_merged(unique_suffix):
    """The exact bug this round fixes: two people with the same name must
    NEVER be treated as one patient just because the name matches. This is
    the core regression test -- if it ever fails, the same-name-collision
    bug is back."""
    org_id = f"pytest-org-identity2-{unique_suffix}"
    phone_a = f"9{unique_suffix}1".rjust(10, "1")[-10:]
    phone_b = f"9{unique_suffix}2".rjust(10, "1")[-10:]
    assert phone_a != phone_b

    patient_a = await resolve_patient_id(org_id, "Ramesh Kumar", phone_a)
    patient_b = await resolve_patient_id(org_id, "Ramesh Kumar", phone_b)
    assert patient_a is not None and patient_b is not None
    assert patient_a != patient_b, "same name + different phone must NOT collapse into one patient"


@pytest.mark.asyncio
async def test_ambiguous_name_with_no_phone_resolves_to_none_not_a_guess(unique_suffix):
    """Two already-distinct patients share a name and neither call supplies
    a phone -- resolve_patient_id must refuse to guess which one this row
    belongs to. Returning None (row stays unlinked) is the safe failure
    mode; silently picking one would risk exactly the cross-contamination
    this module exists to prevent."""
    org_id = f"pytest-org-identity3-{unique_suffix}"
    phone_a = f"9{unique_suffix}3".rjust(10, "1")[-10:]
    phone_b = f"9{unique_suffix}4".rjust(10, "1")[-10:]
    await resolve_patient_id(org_id, "Sunita Joshi", phone_a)
    await resolve_patient_id(org_id, "Sunita Joshi", phone_b)

    ambiguous = await resolve_patient_id(org_id, "Sunita Joshi", None)
    assert ambiguous is None


@pytest.mark.asyncio
async def test_unambiguous_name_with_no_phone_still_resolves(unique_suffix):
    org_id = f"pytest-org-identity4-{unique_suffix}"
    phone_a = f"9{unique_suffix}5".rjust(10, "1")[-10:]
    only = await resolve_patient_id(org_id, "Kavita Iyer", phone_a)
    again = await resolve_patient_id(org_id, "Kavita Iyer", None)
    assert again == only


@pytest.mark.asyncio
async def test_legacy_patient_row_without_keys_is_found_and_self_heals(unique_suffix):
    """A patient document created before phone_key/name_key existed (no
    such fields at all) must still be found by its raw phone, and must get
    the keys stamped on so the NEXT lookup is the fast indexed path
    instead of the legacy fallback scan."""
    org_id = f"pytest-org-legacy-{unique_suffix}"
    phone = f"9{unique_suffix}6".rjust(10, "1")[-10:]
    legacy_id = new_id()
    await patients.insert_one({
        "_id": legacy_id, "org_id": org_id, "name": "Legacy Patient",
        "phone": f"+91-{phone}", "email": None, "age": None, "gender": None,
        "tags": None, "notes": None, "last_visit_at": None, "total_visits": 0,
        "lifetime_value": 0, "created_at": now(), "updated_at": now(),
        # deliberately no phone_key / name_key
    })

    resolved = await resolve_patient_id(org_id, "Legacy Patient", phone)
    assert resolved == legacy_id

    healed = await patients.find_one({"_id": legacy_id})
    assert healed["phone_key"] == phone
    assert healed["name_key"] == "legacy patient"


@pytest.mark.asyncio
async def test_linked_history_filter_matches_new_rows_and_legacy_unlinked_rows_only(unique_suffix):
    org_id = f"pytest-org-hist-{unique_suffix}"
    patient = {"_id": new_id(), "org_id": org_id, "name": "Amit Kulkarni"}
    other_patient_same_name = {"_id": new_id(), "org_id": org_id, "name": "Amit Kulkarni"}

    await appointments.insert_many([
        {"_id": new_id(), "org_id": org_id, "patient_name": "Amit Kulkarni",
         "patient_id": patient["_id"], "appointment_date": "2026-01-01", "status": "scheduled"},
        {"_id": new_id(), "org_id": org_id, "patient_name": "Amit Kulkarni",
         "patient_id": None, "appointment_date": "2026-01-02", "status": "scheduled"},
        {"_id": new_id(), "org_id": org_id, "patient_name": "Amit Kulkarni",
         "patient_id": other_patient_same_name["_id"], "appointment_date": "2026-01-03", "status": "scheduled"},
    ])

    rows = await appointments.find(linked_history_filter(patient)).to_list(None)
    dates = sorted(r["appointment_date"] for r in rows)
    # own linked row + the still-unlinked legacy row -- but NOT the row
    # explicitly linked to the OTHER same-named patient.
    assert dates == ["2026-01-01", "2026-01-02"]


def test_appointment_create_links_patient_id(client, unique_suffix):
    headers, org_id = _sunrise(client)
    phone = f"9{unique_suffix}7".rjust(10, "1")[-10:]
    resp = client.post("/api/appointments", headers=headers, json={
        "patientName": f"Round19 Identity Patient {unique_suffix}",
        "patientPhone": phone, "appointmentDate": "2026-09-01",
    })
    assert resp.status_code == 201, resp.text
    appt = resp.json()["appointment"]
    assert appt.get("patient_id"), "a fresh appointment must be bound to a real patient record, not just a name string"

    patient_view = client.get(f"/api/patients/{appt['patient_id']}", headers=headers)
    assert patient_view.status_code == 200, patient_view.text
    appt_ids = {a["id"] for a in patient_view.json()["appointments"]}
    assert appt["id"] in appt_ids


def test_two_same_named_patients_do_not_see_each_others_history_via_api(client, unique_suffix):
    """End-to-end version of the core regression: book two appointments
    under the identical patient name but different phone numbers, and
    confirm each patient's detail page shows only their own appointment."""
    headers, org_id = _sunrise(client)
    shared_name = f"Round19 Twin {unique_suffix}"
    phone_a = f"9{unique_suffix}8".rjust(10, "1")[-10:]
    phone_b = f"9{unique_suffix}9".rjust(10, "1")[-10:]

    appt_a = client.post("/api/appointments", headers=headers, json={
        "patientName": shared_name, "patientPhone": phone_a, "appointmentDate": "2026-09-02",
    }).json()["appointment"]
    appt_b = client.post("/api/appointments", headers=headers, json={
        "patientName": shared_name, "patientPhone": phone_b, "appointmentDate": "2026-09-03",
    }).json()["appointment"]

    assert appt_a["patient_id"] != appt_b["patient_id"], "same name + different phone must be different patients"

    view_a = client.get(f"/api/patients/{appt_a['patient_id']}", headers=headers).json()
    view_b = client.get(f"/api/patients/{appt_b['patient_id']}", headers=headers).json()
    assert {a["id"] for a in view_a["appointments"]} == {appt_a["id"]}
    assert {a["id"] for a in view_b["appointments"]} == {appt_b["id"]}


def test_link_history_backfill_links_unambiguous_legacy_rows(client, unique_suffix):
    """Simulates the real-world backlog this endpoint exists for: rows
    written before patient_id existed, with only a name+phone. After
    running the backfill, an unambiguous row is linked to a real patient
    and future history joins pick it up; the endpoint itself never errors
    even though these rows were never created through a normal write path
    in this test."""
    headers, org_id = _sunrise(client)
    phone = f"9{unique_suffix}0".rjust(10, "1")[-10:]
    name = f"Round19 Backfill Patient {unique_suffix}"

    async def _seed():
        await appointments.insert_one({
            "_id": new_id(), "org_id": org_id, "patient_name": name, "patient_phone": phone,
            "patient_id": None, "appointment_date": "2026-09-04", "status": "scheduled",
        })

    # TestClient is sync, so the async seed write is driven directly off
    # the event loop rather than via an `async def` test.
    import asyncio
    asyncio.get_event_loop().run_until_complete(_seed())

    resp = client.post("/api/patients/link-history", headers=headers, json={"createMissing": True})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"]["appointments"]["linked"] >= 1

    created_patient = client.get("/api/patients", headers=headers, params={"q": name}).json()["patients"]
    assert len(created_patient) == 1
    patient_id = created_patient[0]["id"]

    detail = client.get(f"/api/patients/{patient_id}", headers=headers).json()
    assert any(a["appointment_date"] == "2026-09-04" for a in detail["appointments"])


# ---------------------------------------------------------------------------
# RENEWAL DUE DATE
# ---------------------------------------------------------------------------

def test_renewal_due_date_matches_the_anchor_day_not_just_the_month():
    started = datetime(2026, 3, 15, tzinfo=timezone.utc)
    due = _renewal_due_date(started, "monthly", "2026-04")
    assert due.year == 2026 and due.month == 4 and due.day == 15


def test_renewal_due_date_clamps_month_end_like_next_renewal_date_does():
    # Subscribed Jan 31 -- February has no 31st, so the due date clamps to
    # the 28th (2026 is not a leap year), same clamp next_renewal_date()
    # already performs for the Plans & Billing display. If these two ever
    # disagreed, the invoice would show a different day than the page that
    # promised it.
    started = datetime(2026, 1, 31, tzinfo=timezone.utc)
    due = _renewal_due_date(started, "monthly", "2026-02")
    assert due.year == 2026 and due.month == 2 and due.day == 28

    # And March, having 31 days again, goes back to the original anchor --
    # the anchor-day fix from round 18 applies here too, not just to
    # next_renewal_date().
    due_march = _renewal_due_date(started, "monthly", "2026-03")
    assert due_march.day == 31


def test_renewal_due_date_is_none_when_period_is_not_actually_due():
    started = datetime(2026, 3, 15, tzinfo=timezone.utc)
    assert _renewal_due_date(started, "monthly", "2026-03") is None  # start period itself
    assert _renewal_due_date(started, "yearly", "2026-06") is None  # wrong month for yearly


def test_generated_renewal_charge_carries_a_due_date_matching_the_anchor_day(client, admin_headers, unique_suffix):
    """End-to-end: seed a subscription with a controlled started_at, run
    the existing (unchanged) admin Generate action, and confirm the
    resulting charge's due_date is the exact anchor day -- not just the
    bare period string it used to be."""
    org_id = f"pytest-org-renewal-{unique_suffix}"
    started_at = datetime(2026, 1, 10, tzinfo=timezone.utc)
    sub_id = new_id()

    async def _seed():
        await organizations.insert_one({
            "_id": org_id, "name": f"Round19 Renewal Test Clinic {unique_suffix}",
            "created_at": now(),
        })
        await organization_subscriptions.insert_one({
            "_id": sub_id, "org_id": org_id, "plan_code": "manage",
            "billing_cycle": "monthly", "status": "active",
            "price_at_purchase": 9999, "started_at": started_at, "created_at": now(),
        })

    async def _deactivate():
        # This is a monthly subscription with a fixed started_at, so it
        # stays "genuinely due" for every real calendar month from here on
        # (see _is_renewal_period_due) -- including whatever month the
        # test suite's OTHER tests happen to run in. POST /generate scans
        # every ACTIVE subscription platform-wide with no per-test
        # isolation (that global scan is real, deliberate product
        # behaviour), so leaving this one active would let it show up in
        # an unrelated test's generate call for the real current period
        # (see test_subscription_renewals.py's own start-period test).
        # Deactivating it once this test is done keeps the shared session
        # DB clean for whichever test runs next, the same discipline every
        # other test in this suite that creates an active subscription
        # already follows.
        await organization_subscriptions.update_one({"_id": sub_id}, {"$set": {"status": "cancelled"}})

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_seed())
    try:
        resp = client.post("/api/subscription-renewals/generate", headers=admin_headers, json={"period": "2026-02"})
        assert resp.status_code == 201, resp.text

        rows = client.get("/api/subscription-renewals", headers=admin_headers, params={"orgId": org_id, "period": "2026-02"}).json()["renewals"]
        assert len(rows) == 1
        due_date = rows[0]["due_date"]
        assert due_date is not None
        assert due_date.startswith("2026-02-10"), f"expected due date anchored on the 10th, got {due_date}"
    finally:
        loop.run_until_complete(_deactivate())


def test_legacy_renewal_charge_without_due_date_still_lists_and_downloads(client, admin_headers, unique_suffix):
    """A charge generated before round 19 has no due_date field at all.
    Nothing about listing it, marking it paid, or downloading its invoice
    should break just because that field is now expected on new rows --
    this is the "no claw-back, nothing re-billed" guarantee in practice."""
    org_id = f"pytest-org-legacy-renewal-{unique_suffix}"
    charge_id = new_id()

    async def _seed():
        await organizations.insert_one({"_id": org_id, "name": "Legacy Renewal Org", "created_at": now()})
        await subscription_renewals.insert_one({
            "_id": charge_id, "org_id": org_id, "org_name": "Legacy Renewal Org",
            "subscription_id": new_id(), "plan_code": "manage", "plan_name": "MANAGE",
            "billing_cycle": "monthly", "period": "2025-11",
            "amount": 9999, "invoice_number": f"SUB-INV-LEGACY-{unique_suffix}",
            "status": "paid", "payer_marked_paid_at": now(), "payment_reference": "LEGACY-REF",
            "confirmed_by": "internal_override", "paid_at": now(),
            "created_by": "system", "created_at": now(),
            # deliberately NO due_date field, simulating a pre-round-19 row
        })

    import asyncio
    asyncio.get_event_loop().run_until_complete(_seed())

    listed = client.get("/api/subscription-renewals", headers=admin_headers, params={"orgId": org_id}).json()["renewals"]
    assert len(listed) == 1
    assert listed[0].get("due_date") is None

    invoice = client.get(f"/api/subscription-renewals/{charge_id}/invoice", headers=admin_headers)
    assert invoice.status_code == 200, invoice.text
    assert invoice.content[:5] == b"%PDF-"

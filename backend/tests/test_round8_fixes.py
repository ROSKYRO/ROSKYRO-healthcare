"""Regression tests for round 8's fixes:

1. Regex-injection crashes: several search endpoints (orgs.py, patients.py,
   referrals.py, partners.py's search-by-service) built a Mongo $regex
   filter directly from raw user-typed search text with no re.escape().
   A search term containing a regex metacharacter (an unbalanced "(", a
   stray "*", etc.) crashed the endpoint with an unhandled re.error
   instead of just matching that literal text.

2. Unvalidated numeric fields: doctors.py's PATCH /doctors/{id} accepted
   consultationFee/slotDurationMinutes/capacityPerSlot with no type
   coercion (unlike create_doctor, which validates these the same way),
   and appointments.py's create_appointment/patch_appointment accepted
   revenueAmount with none at all. A non-numeric value stored this way
   didn't fail at write time -- it silently corrupted the record, then
   crashed the FIRST downstream read that called float() on it (public
   booking for a bad doctor fee; the dashboard's revenue total and the
   appointments PDF/report for a bad revenue_amount).

3. Partnerships TOCTOU race: _set_partnership (partnerships.py) ends
   whatever partnership was active for an (org_id, category_id) before
   inserting the new active row -- two concurrent calls could both pass
   that step and both insert an active row, breaking the module's own
   documented "at most one active partnership per (org, category)"
   invariant. Fixed with a partial unique index (app/db_indexes.py) scoped
   to status="active", paired with a try/except DuplicateKeyError that
   turns a genuine race loss into a clean 409 instead of a raw 500 --
   mirroring the same pattern already used for the settlement/renewal
   races fixed in an earlier round.
"""
import pytest

from app.db import partnerships, appointments as appointments_col
from app.utils.ids import new_id, now

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# --- 1. Regex-injection: a search term with regex metacharacters must not crash ---

@pytest.mark.parametrize("bad_term", ["(", "a(b", "[unterminated", "a**b", "a+++"])
def test_org_search_survives_regex_metacharacters(client, admin_headers, bad_term):
    resp = client.get("/api/orgs", headers=admin_headers, params={"q": bad_term})
    assert resp.status_code == 200, resp.text


def test_patient_search_survives_regex_metacharacters(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.get("/api/patients", headers=headers, params={"q": "("})
    assert resp.status_code == 200, resp.text


def test_referral_search_survives_regex_metacharacters(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.get("/api/referrals", headers=headers, params={"q": "("})
    assert resp.status_code == 200, resp.text


def test_partner_search_by_service_survives_regex_metacharacters(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.get("/api/partners/search-by-service", headers=headers, params={"keyword": "("})
    assert resp.status_code == 200, resp.text


def test_org_search_still_matches_normal_substrings(client, admin_headers):
    """Sanity check the fix didn't break normal search -- re.escape() only
    changes how metacharacters are treated, plain substrings still match
    the same as before."""
    resp = client.get("/api/orgs", headers=admin_headers, params={"q": "sunrise"})
    assert resp.status_code == 200, resp.text
    names = [o["name"].lower() for o in resp.json()["organizations"]]
    assert any("sunrise" in n for n in names)


# --- 2. Numeric field validation on doctors.py / appointments.py ---

def test_patch_doctor_rejects_non_numeric_consultation_fee(client):
    headers = _login(client, SUNRISE_EMAIL)
    doctors_resp = client.get("/api/doctors", headers=headers)
    assert doctors_resp.status_code == 200, doctors_resp.text
    doctor_id = doctors_resp.json()["doctors"][0]["id"]

    resp = client.patch(f"/api/doctors/{doctor_id}", headers=headers, json={"consultationFee": "abc"})
    assert resp.status_code == 400, resp.text
    assert "numeric" in resp.json()["error"].lower()


def test_patch_doctor_accepts_and_coerces_numeric_string(client):
    """A numeric-looking value (e.g. "750" from a form field that always
    submits strings) must still work -- only genuinely non-numeric values
    should be rejected."""
    headers = _login(client, SUNRISE_EMAIL)
    doctor_id = client.get("/api/doctors", headers=headers).json()["doctors"][0]["id"]

    resp = client.patch(f"/api/doctors/{doctor_id}", headers=headers, json={"consultationFee": "750"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["doctor"]["consultation_fee"] == 750.0


def test_create_appointment_rejects_non_numeric_revenue_amount(client):
    headers = _login(client, SUNRISE_EMAIL)
    resp = client.post("/api/appointments", headers=headers, json={
        "patientName": "Regression Test Patient", "appointmentDate": "2026-09-01", "revenueAmount": "not-a-number",
    })
    assert resp.status_code == 400, resp.text
    assert "numeric" in resp.json()["error"].lower()


def test_patch_appointment_rejects_non_numeric_revenue_amount(client):
    headers = _login(client, SUNRISE_EMAIL)
    created = client.post("/api/appointments", headers=headers, json={
        "patientName": "Regression Test Patient 2", "appointmentDate": "2026-09-02", "revenueAmount": 500,
    })
    assert created.status_code == 201, created.text
    appt_id = created.json()["appointment"]["id"]

    resp = client.patch(f"/api/appointments/{appt_id}", headers=headers, json={"revenueAmount": "bad"})
    assert resp.status_code == 400, resp.text
    assert "numeric" in resp.json()["error"].lower()

    # the appointment's original (valid) revenue_amount must be unchanged --
    # a rejected PATCH must not partially apply.
    unchanged = client.get("/api/appointments", headers=headers).json()["appointments"]
    match = next(a for a in unchanged if a["id"] == appt_id)
    assert match["revenue_amount"] == 500


@pytest.mark.asyncio
async def test_revenue_amount_never_stored_as_non_numeric_directly():
    """Direct DB-level check that a bad revenue_amount, if it HAD been
    stored (pre-fix), would indeed crash the downstream float() call this
    fix protects against -- documents the exact failure mode being
    guarded against, independent of the HTTP-level 400 tests above."""
    doc_id = new_id()
    await appointments_col.insert_one({
        "_id": doc_id, "org_id": "pytest-org", "patient_name": "p", "patient_phone": None,
        "doctor_name": None, "appointment_date": "2026-09-03", "appointment_time": None,
        "status": "completed", "source": "walk_in", "is_new_patient": True,
        "revenue_amount": "deliberately-bad-value", "booked_via": None, "token_number": None,
        "payment_status": "not_required", "payment_amount": None, "patient_note": None, "created_at": now(),
    })
    doc = await appointments_col.find_one({"_id": doc_id})
    with pytest.raises(ValueError):
        float(doc["revenue_amount"])
    # cleanup -- this synthetic row would otherwise pollute dashboard.py's
    # platform-wide revenue aggregations for any test/usage that scans all
    # appointments regardless of org.
    await appointments_col.delete_one({"_id": doc_id})


# --- 3. Partnerships partial-unique-index race backstop ---

@pytest.mark.asyncio
async def test_partnerships_partial_unique_index_enforced(client):
    """`client` fixture guarantees ensure_indexes() has already run.
    Directly proves the partial unique index on (org_id, category_id)
    WHERE status="active" rejects a genuine duplicate-active-row insert
    (the scenario _set_partnership's try/except now handles gracefully),
    while still allowing multiple ENDED rows for the same org+category
    (expected -- every partner swap leaves a historical ended row)."""
    from pymongo.errors import DuplicateKeyError

    org_id = f"pytest-partnership-org-{new_id()}"
    category_id = f"pytest-category-{new_id()}"

    await partnerships.insert_one({
        "_id": new_id(), "org_id": org_id, "category_id": category_id, "partner_id": "p1",
        "status": "active", "initiated_by": "business",
        "created_at": now(), "ended_at": None, "ended_by": None, "ended_reason": None,
    })
    with pytest.raises(DuplicateKeyError):
        await partnerships.insert_one({
            "_id": new_id(), "org_id": org_id, "category_id": category_id, "partner_id": "p2",
            "status": "active", "initiated_by": "business",
            "created_at": now(), "ended_at": None, "ended_by": None, "ended_reason": None,
        })

    # Ended rows for the same (org, category) must NOT collide with each
    # other or with the still-active row above -- the index is partial.
    await partnerships.insert_one({
        "_id": new_id(), "org_id": org_id, "category_id": category_id, "partner_id": "p3",
        "status": "ended", "initiated_by": "business",
        "created_at": now(), "ended_at": now(), "ended_by": "u1", "ended_reason": "replaced",
    })
    await partnerships.insert_one({
        "_id": new_id(), "org_id": org_id, "category_id": category_id, "partner_id": "p4",
        "status": "ended", "initiated_by": "business",
        "created_at": now(), "ended_at": now(), "ended_by": "u1", "ended_reason": "replaced",
    })


def test_set_partnership_http_still_works_normally(client):
    """Sanity check against the live API: the normal (non-racing) set/swap
    flow must still succeed exactly as before -- the fix must not have
    broken the one-request-at-a-time case that test_partnerships.py
    already covers in more detail."""
    headers = _login(client, SUNRISE_EMAIL)
    candidates = client.get("/api/partners/search-by-service", headers=headers, params={"keyword": "blood"}).json()["partners"]
    assert len(candidates) >= 1
    resp = client.post("/api/partnerships", headers=headers, json={"partnerId": candidates[0]["id"]})
    assert resp.status_code == 201, resp.text

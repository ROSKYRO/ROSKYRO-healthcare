"""Regression tests for the cross-tenant authorization bugs found and
fixed in a full security/correctness audit (see the PATCH endpoints in
patients.py/billing.py/followups.py/queue.py/appointments.py, the
partner-org-override bug repeated across billing.py/followups.py/queue.py/
reviews.py/reports.py/appointments.py, approvals.py's decide_approval, and
referrals.py's transition/timeline endpoints). Every test here asserts the
FIXED (secure) behavior -- if any of these regress back to their old
behavior, these tests catch it."""
DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"  # owner, MANAGE + CONNECT pillars
VITAL_SKIN_EMAIL = "vital.skin...aesthetics@example.com"  # owner, different org, also MANAGE
SMILE_DENTAL_EMAIL = "smile.bright.dental@example.com"  # owner, different org, GROW + CONNECT (not MANAGE)
CITYSCAN_PARTNER_EMAIL = "admin.cityscan.diagnostics@example.com"  # partner shell


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(login_resp):
    return {"Authorization": f"Bearer {login_resp['token']}"}


def test_patch_patient_is_scoped_to_the_owning_business(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    sunrise_headers = _headers(sunrise)
    created = client.post("/api/patients", headers=sunrise_headers, json={"name": f"Sec Test Patient {unique_suffix}"})
    assert created.status_code == 201, created.text
    patient_id = created.json()["patient"]["id"]

    vital_skin = _login(client, VITAL_SKIN_EMAIL)
    cross_org_patch = client.patch(f"/api/patients/{patient_id}", headers=_headers(vital_skin), json={"name": "Hijacked"})
    assert cross_org_patch.status_code == 403, cross_org_patch.text

    own_patch = client.patch(f"/api/patients/{patient_id}", headers=sunrise_headers, json={"name": "Updated Name"})
    assert own_patch.status_code == 200, own_patch.text
    assert own_patch.json()["patient"]["name"] == "Updated Name"


def test_patch_invoice_is_scoped_to_the_owning_business(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    sunrise_headers = _headers(sunrise)
    created = client.post("/api/billing", headers=sunrise_headers, json={
        "patientName": f"Sec Test Invoice {unique_suffix}",
        "lineItems": [{"description": "Consultation", "quantity": 1, "unitPrice": 500}],
    })
    assert created.status_code == 201, created.text
    invoice_id = created.json()["invoice"]["id"]

    vital_skin = _login(client, VITAL_SKIN_EMAIL)
    cross_org_patch = client.patch(f"/api/billing/{invoice_id}", headers=_headers(vital_skin), json={"status": "paid"})
    assert cross_org_patch.status_code == 403, cross_org_patch.text


def test_patch_followup_is_scoped_to_the_owning_business(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    sunrise_headers = _headers(sunrise)
    created = client.post("/api/followups", headers=sunrise_headers, json={
        "patientName": f"Sec Test Followup {unique_suffix}", "reason": "Review", "dueDate": "2026-08-01",
    })
    assert created.status_code == 201, created.text
    followup_id = created.json()["followup"]["id"]

    vital_skin = _login(client, VITAL_SKIN_EMAIL)
    cross_org_patch = client.patch(f"/api/followups/{followup_id}", headers=_headers(vital_skin), json={"status": "done"})
    assert cross_org_patch.status_code == 403, cross_org_patch.text


def test_patch_queue_entry_is_scoped_to_the_owning_business(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    sunrise_headers = _headers(sunrise)
    created = client.post("/api/queue", headers=sunrise_headers, json={"patientName": f"Sec Test Queue {unique_suffix}"})
    assert created.status_code == 201, created.text
    entry_id = created.json()["entry"]["id"]

    vital_skin = _login(client, VITAL_SKIN_EMAIL)
    cross_org_patch = client.patch(f"/api/queue/{entry_id}", headers=_headers(vital_skin), json={"status": "done"})
    assert cross_org_patch.status_code == 403, cross_org_patch.text


def test_queue_check_in_assigns_unique_sequential_tokens(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    first = client.post("/api/queue", headers=headers, json={"patientName": f"Token Test A {unique_suffix}"})
    second = client.post("/api/queue", headers=headers, json={"patientName": f"Token Test B {unique_suffix}"})
    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["entry"]["token_number"] > first.json()["entry"]["token_number"]


def test_patch_appointment_is_scoped_to_the_owning_business(client, unique_suffix):
    sunrise = _login(client, SUNRISE_EMAIL)
    sunrise_headers = _headers(sunrise)
    created = client.post("/api/appointments", headers=sunrise_headers, json={
        "patientName": f"Sec Test Appt {unique_suffix}", "appointmentDate": "2026-08-01",
    })
    assert created.status_code == 201, created.text
    appt_id = created.json()["appointment"]["id"]

    vital_skin = _login(client, VITAL_SKIN_EMAIL)
    cross_org_patch = client.patch(f"/api/appointments/{appt_id}", headers=_headers(vital_skin), json={"status": "completed"})
    assert cross_org_patch.status_code == 403, cross_org_patch.text


def test_partner_cannot_override_orgid_on_business_list_endpoints(client):
    """A partner-shell account previously fell into the same `else orgId`
    branch internal used, so it could pass an arbitrary ?orgId= and read
    another business's data on these endpoints. Now rejected with 400
    (same as a partner passing no orgId at all -- it never had a
    legitimate one)."""
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    partner = _login(client, CITYSCAN_PARTNER_EMAIL)
    partner_headers = _headers(partner)

    for path in (
        "/api/billing", "/api/followups", "/api/queue", "/api/reviews", "/api/reports", "/api/appointments",
        "/api/patients", "/api/whatsapp", "/api/doctors",
    ):
        resp = client.get(path, headers=partner_headers, params={"orgId": org_id})
        assert resp.status_code == 400, f"{path}: expected 400, got {resp.status_code}: {resp.text}"


def test_get_patient_is_scoped_to_the_owning_business(client, unique_suffix):
    """GET /patients/{id} previously only rejected a MISMATCHED customer --
    a partner-shell account (never checked at all) could fetch any
    patient's full record plus appointments/follow-ups/invoices/WhatsApp
    history for a business it has no relationship with."""
    sunrise = _login(client, SUNRISE_EMAIL)
    sunrise_headers = _headers(sunrise)
    created = client.post("/api/patients", headers=sunrise_headers, json={"name": f"Sec Test Patient GET {unique_suffix}"})
    assert created.status_code == 201, created.text
    patient_id = created.json()["patient"]["id"]

    partner = _login(client, CITYSCAN_PARTNER_EMAIL)
    forbidden = client.get(f"/api/patients/{patient_id}", headers=_headers(partner))
    assert forbidden.status_code == 403, forbidden.text

    vital_skin = _login(client, VITAL_SKIN_EMAIL)
    cross_org = client.get(f"/api/patients/{patient_id}", headers=_headers(vital_skin))
    assert cross_org.status_code == 403, cross_org.text

    own = client.get(f"/api/patients/{patient_id}", headers=sunrise_headers)
    assert own.status_code == 200, own.text


def test_get_org_and_team_are_scoped_to_the_owning_business(client):
    """GET /orgs/{id} and GET /orgs/{id}/team previously only rejected a
    MISMATCHED customer -- a partner-shell account (never checked at all)
    could fetch any business's full contact/billing record or staff
    roster."""
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    partner = _login(client, CITYSCAN_PARTNER_EMAIL)
    partner_headers = _headers(partner)

    forbidden_org = client.get(f"/api/orgs/{org_id}", headers=partner_headers)
    assert forbidden_org.status_code == 403, forbidden_org.text

    forbidden_team = client.get(f"/api/orgs/{org_id}/team", headers=partner_headers)
    assert forbidden_team.status_code == 403, forbidden_team.text

    own_org = client.get(f"/api/orgs/{org_id}", headers=_headers(sunrise))
    assert own_org.status_code == 200, own_org.text

    admin = _login(client, "admin@roskyro.com")
    internal_org = client.get(f"/api/orgs/{org_id}", headers=_headers(admin))
    assert internal_org.status_code == 200, internal_org.text


def test_approval_decision_is_scoped_to_the_owning_business(client):
    """A partner-shell account previously fell straight through
    decide_approval's ownership check (which only fired for a mismatched
    *customer*) and could approve/reject any business's pending approval."""
    sunrise = _login(client, SUNRISE_EMAIL)
    org_id = sunrise["user"]["orgId"]
    admin = _login(client, "admin@roskyro.com")
    admin_headers = _headers(admin)

    created = client.post("/api/approvals", headers=admin_headers, json={
        "orgId": org_id, "approvalType": "content_post", "title": "Security regression test approval",
    })
    assert created.status_code == 201, created.text
    approval_id = created.json()["approval"]["id"]

    partner = _login(client, CITYSCAN_PARTNER_EMAIL)
    forbidden = client.post(f"/api/approvals/{approval_id}/decision", headers=_headers(partner), json={"decision": "approved"})
    assert forbidden.status_code == 403, forbidden.text

    sunrise_headers = _headers(sunrise)
    allowed = client.post(f"/api/approvals/{approval_id}/decision", headers=sunrise_headers, json={"decision": "approved"})
    assert allowed.status_code == 200, allowed.text


def test_referral_timeline_is_scoped_to_the_involved_parties(client):
    """GET /referrals/{id}/timeline previously took no current_user at all
    -- any authenticated ROSKYRO user could pull any other business's
    referral history."""
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    candidates = client.get("/api/partners/search-by-service", headers=headers, params={"keyword": "blood"}).json()["partners"]
    assert candidates
    created = client.post("/api/referrals", headers=headers, json={
        "partnerId": candidates[0]["id"], "patientName": "Timeline Sec Test Patient",
        "serviceRequested": "Blood Test",
    })
    assert created.status_code == 201, created.text
    referral_id = created.json()["referral"]["id"]

    own_timeline = client.get(f"/api/referrals/{referral_id}/timeline", headers=headers)
    assert own_timeline.status_code == 200, own_timeline.text

    # Needs another business that also has the CONNECT pillar active (so
    # this actually exercises the ownership check below, rather than
    # being short-circuited by the router's require_plan("connect") 402).
    other_business = _login(client, SMILE_DENTAL_EMAIL)
    other_business_timeline = client.get(f"/api/referrals/{referral_id}/timeline", headers=_headers(other_business))
    assert other_business_timeline.status_code == 403, other_business_timeline.text


def test_invoice_with_non_numeric_line_item_returns_clean_400(client, unique_suffix):
    """A non-numeric quantity/unitPrice/discount/taxRate previously raised
    an unhandled ValueError from float()/int() in compute_totals, which
    surfaced as a raw unhandled-exception 500 instead of a normal
    validation error."""
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    resp = client.post("/api/billing", headers=headers, json={
        "patientName": f"Bad Invoice {unique_suffix}",
        "lineItems": [{"description": "Consultation", "quantity": "not-a-number", "unitPrice": 500}],
    })
    assert resp.status_code == 400, resp.text


def test_create_doctor_with_non_numeric_fee_returns_clean_400(client, unique_suffix):
    """Same fix as the invoice case above, applied to POST /doctors'
    consultationFee/slotDurationMinutes/capacityPerSlot conversions."""
    sunrise = _login(client, SUNRISE_EMAIL)
    headers = _headers(sunrise)
    resp = client.post("/api/doctors", headers=headers, json={
        "name": f"Dr. Bad Fee {unique_suffix}",
        "consultationFee": "not-a-number",
        "weeklySchedule": [{"day": "mon", "openTime": "09:00", "closeTime": "17:00"}],
    })
    assert resp.status_code == 400, resp.text


def test_login_identifier_is_not_a_regex_injection_vector(client):
    """re.escape() fix: a login identifier containing regex metacharacters
    must not match by pattern -- only ever an exact (case-insensitive)
    match, or no match at all."""
    resp = client.post("/api/auth/login", json={"identifier": ".*", "password": DEMO_PASSWORD})
    assert resp.status_code == 401, resp.text

    # Sanity: a real account with special regex chars nowhere in it still
    # logs in normally after the escaping change.
    normal = client.post("/api/auth/login", json={"identifier": SUNRISE_EMAIL, "password": DEMO_PASSWORD})
    assert normal.status_code == 200, normal.text

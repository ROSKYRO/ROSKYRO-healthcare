"""Regression tests for round 22 -- the Register page's Business Type /
Business Category rewrite (app/utils/business_taxonomy.py).

Before this round, business_type WAS the specialty (clinic/dental/
skin_clinic/eye_hospital/etc) and business_category was a separate,
independent size/scale picker (solo_doctor/clinic/hospital). This round
flips it: business_type is now the broad kind of healthcare organization
(Hospital, Clinic, Diagnostic Center, Pharmacy, ...) and business_category
is a specialty dropdown dependent on whichever business_type was picked.

Three things this file checks:
1. Registration accepts the new taxonomy's (type, category) pairs and they
   round-trip correctly through /me.
2. The OLD business_category values (solo_doctor/clinic/hospital) and the
   default-when-omitted behaviour still work -- nothing already relying on
   the old, looser semantics should break.
3. The referral-creation business-type gate (REFERRAL_CREATOR_BUSINESS_TYPES
   in routers/referrals.py) still behaves the same for the two old business
   types that are also new-taxonomy top-level types (clinic, hospital), and
   the new "eye_care_center" type -- added specifically as the new home for
   the old "eye_hospital" business_type's referral-creation right -- has that
   right, while an unrelated new type (dental_center) does NOT gain it.
"""
import itertools

DEMO_PASSWORD = "Roskyro@123"
_reg_counter = itertools.count(1)


def _register(client, unique_suffix, **overrides):
    n = next(_reg_counter)
    body = {
        "orgName": f"Round22 Test Org {unique_suffix}{n}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": "Dr. Round22 Test",
        "email": f"round22.test.{unique_suffix}{n}@example.com",
        "phone": f"96{unique_suffix}{n}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    }
    body.update(overrides)
    resp = client.post("/api/auth/register", json=body)
    return resp


def _headers(reg_json):
    return {"Authorization": f"Bearer {reg_json['token']}"}


def _first_partner_id(client, headers):
    resp = client.get("/api/partners", headers=headers)
    assert resp.status_code == 200, resp.text
    partners = resp.json()["partners"]
    assert partners, "expected at least one seeded partner"
    return partners[0]["id"]


def _activate_connect(client, headers):
    resp = client.post("/api/plans/subscribe", json={"planCode": "connect"}, headers=headers)
    assert resp.status_code == 201, resp.text


def test_new_taxonomy_type_and_category_pair_round_trips(client, unique_suffix):
    resp = _register(client, unique_suffix, businessType="diagnostic_center", businessCategory="full_diagnostic_center")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["businessType"] == "diagnostic_center"
    assert body["user"]["businessCategory"] == "full_diagnostic_center"

    me = client.get("/api/auth/me", headers=_headers(body)).json()["user"]
    assert me["businessType"] == "diagnostic_center"
    assert me["businessCategory"] == "full_diagnostic_center"


def test_hospital_type_accepts_its_specialty_categories(client, unique_suffix):
    for category in ("cardiac_hospital", "trauma_center", "eye_hospital"):
        resp = _register(client, unique_suffix, businessType="hospital", businessCategory=category)
        assert resp.status_code == 201, resp.text
        assert resp.json()["user"]["businessCategory"] == category


def test_imaging_center_type_accepts_its_categories(client, unique_suffix):
    resp = _register(client, unique_suffix, businessType="imaging_center", businessCategory="mri")
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["businessCategory"] == "mri"


def test_business_type_with_no_specific_breakdown_falls_back_to_itself(client, unique_suffix):
    """Pharmacy has no product-specified sub-category breakdown -- its only
    valid category is itself, matching the frontend's single-option fallback."""
    resp = _register(client, unique_suffix, businessType="pharmacy", businessCategory="pharmacy")
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["businessType"] == "pharmacy"
    assert resp.json()["user"]["businessCategory"] == "pharmacy"


def test_legacy_category_values_and_default_still_work(client, unique_suffix):
    """Pre-round-22 behaviour must not regress: solo_doctor/clinic/hospital
    remain valid businessCategory values, and omitting it still defaults to
    "clinic"."""
    resp = _register(client, unique_suffix, businessCategory="solo_doctor")
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["businessCategory"] == "solo_doctor"

    body = {
        "orgName": f"Round22 No Category {unique_suffix}",
        "businessType": "clinic",
        "ownerName": "Dr. No Category",
        "email": f"round22.nocategory.{unique_suffix}@example.com",
        "phone": f"95{unique_suffix}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    }
    resp = client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    assert resp.json()["user"]["businessCategory"] == "clinic"


def test_unknown_business_category_is_still_rejected(client, unique_suffix):
    resp = _register(client, unique_suffix, businessCategory="not_a_real_specialty_xyz")
    assert resp.status_code == 400, resp.text
    assert "category" in resp.json()["error"].lower()


def test_eye_care_center_type_gains_referral_creation_right(client, unique_suffix):
    """New standalone type added in round 22 -- the direct successor to the
    old "eye_hospital" business_type, so it must be able to create referrals
    just like that old type could."""
    reg = _register(client, unique_suffix, businessType="eye_care_center", businessCategory="eye_care_center")
    assert reg.status_code == 201, reg.text
    headers = _headers(reg.json())
    _activate_connect(client, headers)
    partner_id = _first_partner_id(client, headers)

    resp = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id,
        "patientName": "Round22 Eye Care Patient",
        "serviceRequested": "Cataract Screening",
    })
    assert resp.status_code == 201, resp.text


def test_new_unrelated_business_type_does_not_gain_referral_creation_right(client, unique_suffix):
    """dental_center is a brand-new round-22 top-level type with no old-
    taxonomy equivalent that had referral rights -- it must NOT silently
    gain a right the old "dental" business_type never had."""
    reg = _register(client, unique_suffix, businessType="dental_center", businessCategory="dental_center")
    assert reg.status_code == 201, reg.text
    headers = _headers(reg.json())
    _activate_connect(client, headers)
    partner_id = _first_partner_id(client, headers)

    resp = client.post("/api/referrals", headers=headers, json={
        "partnerId": partner_id,
        "patientName": "Round22 Dental Patient",
        "serviceRequested": "Root Canal",
    })
    assert resp.status_code == 403, resp.text


def test_hospital_and_clinic_types_keep_referral_creation_right(client, unique_suffix):
    """The two business_type slugs that carry over unchanged from the old
    taxonomy (clinic, hospital) must keep working exactly as before."""
    for business_type in ("clinic", "hospital"):
        reg = _register(client, unique_suffix, businessType=business_type, businessCategory=business_type if business_type == "clinic" else "general_hospital")
        assert reg.status_code == 201, reg.text
        headers = _headers(reg.json())
        _activate_connect(client, headers)
        partner_id = _first_partner_id(client, headers)

        resp = client.post("/api/referrals", headers=headers, json={
            "partnerId": partner_id,
            "patientName": f"Round22 {business_type} Patient",
            "serviceRequested": "General Consultation",
        })
        assert resp.status_code == 201, resp.text

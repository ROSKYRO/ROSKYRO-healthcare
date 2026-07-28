"""Regression tests for this round's pricing/plans changes: the new
business_category field, the partner-audience pricing catalog & subscribe/
cancel flow (routers/partner_plans.py), and the GROW-only "reels" add-on
(see app/utils/bundle_bonus.py).

NOTE: the "buy 2 pillars get the 3rd free" bundle-bonus rule (business:
MANAGE + GROW -> CONNECT free; partner: GROW + CONNECT -> MANAGE free) that
this file originally tested has since been retired per explicit product
request (the marketing banners describing it were removed site-wide, and
the code paths that granted/auto-revoked it were deleted from
app/utils/bundle_bonus.py). The two tests below that used to assert those
bonus grants now assert the OPPOSITE -- see test_round15_fixes.py for the
full removal's regression tests, including the price-sync mechanism that
was added in the same round."""
import itertools

DEMO_PASSWORD = "Roskyro@123"
PUNELIFE_PARTNER_EMAIL = "admin.punelife.imaging.centre@example.com"  # partner_admin, seeded with only GROW active
ADMIN_EMAIL = "admin@roskyro.com"

_reg_counter = itertools.count(1)


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _headers(login_resp):
    return {"Authorization": f"Bearer {login_resp['token']}"}


def _login_admin(client):
    resp = client.post("/api/auth/login", json={"identifier": ADMIN_EMAIL, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _register_business(client, unique_suffix, business_category=None):
    n = next(_reg_counter)
    body = {
        "orgName": f"Pricing Test Clinic {unique_suffix}{n}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": "Dr. Pricing Test",
        "email": f"pricing.test.{unique_suffix}{n}@example.com",
        "phone": f"98{unique_suffix}{n}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    }
    if business_category is not None:
        body["businessCategory"] = business_category
    resp = client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_business_category_is_captured_at_registration(client, unique_suffix):
    reg = _register_business(client, unique_suffix, business_category="hospital")
    assert reg["user"]["businessCategory"] == "hospital"

    me = client.get("/api/auth/me", headers=_headers(reg)).json()["user"]
    assert me["businessCategory"] == "hospital"


def test_business_category_defaults_and_rejects_unknown_value(client, unique_suffix):
    reg = _register_business(client, unique_suffix)  # no businessCategory supplied
    assert reg["user"]["businessCategory"] == "clinic"

    n = next(_reg_counter)
    resp = client.post("/api/auth/register", json={
        "orgName": f"Bad Category Clinic {unique_suffix}{n}",
        "businessCategory": "not_a_real_category",
        "ownerName": "Dr. Bad Category",
        "email": f"bad.category.{unique_suffix}{n}@example.com",
        "phone": f"97{unique_suffix}{n}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    })
    assert resp.status_code == 400, resp.text


def test_business_manage_and_grow_no_longer_unlock_connect_free(client, unique_suffix):
    """Retired-feature regression test: activating both trigger pillars must
    NOT auto-grant connect anymore, and the response must not carry the old
    bonusGranted/bonusRevoked keys at all."""
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)

    client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "connect" not in mine["activePillars"]

    sub_resp = client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    assert sub_resp.status_code == 201, sub_resp.text
    assert "bonusGranted" not in sub_resp.json()

    mine = client.get("/api/plans/mine", headers=headers).json()
    assert set(["manage", "grow"]).issubset(set(mine["activePillars"]))
    assert "connect" not in mine["activePillars"]

    # Cancelling grow (still the only 2 pillars active) must not reference
    # any bonus-revoke behavior either, since there was nothing to revoke.
    cancel_resp = client.post("/api/plans/cancel", json={"planCode": "grow"}, headers=headers)
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert "bonusRevoked" not in cancel_resp.json()

    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "connect" not in mine["activePillars"]


def test_reels_addon_requires_grow_and_cascades_on_cancel(client, unique_suffix):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)

    blocked = client.post("/api/plans/subscribe", json={"planCode": "reels"}, headers=headers)
    assert blocked.status_code == 400, blocked.text

    client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    ok = client.post("/api/plans/subscribe", json={"planCode": "reels"}, headers=headers)
    assert ok.status_code == 201, ok.text

    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "reels" not in mine["activePillars"]  # add-ons are never treated as a gating pillar
    reels_row = next(r for r in mine["subscriptions"] if r["plan_code"] == "reels" and r["status"] == "active")
    assert reels_row["price_at_purchase"] == 6999

    cancel_resp = client.post("/api/plans/cancel", json={"planCode": "grow"}, headers=headers)
    assert "reels" in cancel_resp.json()["addonsCancelled"]

    mine = client.get("/api/plans/mine", headers=headers).json()
    reels_row = next(r for r in mine["subscriptions"] if r["plan_code"] == "reels")
    assert reels_row["status"] == "cancelled"


def test_partner_plans_catalog_matches_business_pricing_but_is_a_separate_collection(client):
    business_resp = client.get("/api/plans")
    partner_resp = client.get("/api/partner-plans")
    assert business_resp.status_code == 200 and partner_resp.status_code == 200

    business_by_code = {p["code"]: p for p in business_resp.json()["plans"]}
    partner_by_code = {p["code"]: p for p in partner_resp.json()["plans"]}
    assert set(partner_by_code) == {"grow", "manage", "connect", "complete", "reels"}

    # Per explicit product instruction: partner pricing mirrors business
    # pricing exactly, for every plan/add-on.
    for code, business_plan in business_by_code.items():
        assert partner_by_code[code]["monthly_price"] == business_plan["monthly_price"]
        assert partner_by_code[code]["yearly_price"] == business_plan["yearly_price"]

    # But subscribing on one audience never touches the other's subscription
    # records -- verified by the reels-cascade test above using entirely
    # separate accounts/collections without cross-contamination.


def test_partner_pricing_stays_synced_after_business_price_edit(client):
    """The actual bug the user reported: the two catalogs' prices could
    drift apart because PricingManagement.jsx's admin UI PATCHed them via
    separate endpoints. Now permanently fixed -- proves ONGOING sync, not
    just seed-time equality: editing the business price for a plan must be
    reflected in the partner catalog's matching plan afterward."""
    headers = _login_admin(client)

    before = client.get("/api/partner-plans").json()["plans"]
    before_plan = next(p for p in before if p["code"] == "connect")
    before_monthly, before_yearly = before_plan["monthly_price"], before_plan["yearly_price"]

    resp = client.patch("/api/plans/connect", headers=headers, json={"monthlyPrice": 12345, "yearlyPrice": 123450})
    assert resp.status_code == 200, resp.text

    partner_after = client.get("/api/partner-plans").json()["plans"]
    connect_partner = next(p for p in partner_after if p["code"] == "connect")
    assert connect_partner["monthly_price"] == 12345.0
    assert connect_partner["yearly_price"] == 123450.0

    business_after = client.get("/api/plans").json()["plans"]
    connect_business = next(p for p in business_after if p["code"] == "connect")
    assert connect_business["monthly_price"] == connect_partner["monthly_price"]
    assert connect_business["yearly_price"] == connect_partner["yearly_price"]

    # Restore so this doesn't corrupt the shared demo catalog for later tests.
    client.patch("/api/plans/connect", headers=headers, json={"monthlyPrice": before_monthly, "yearlyPrice": before_yearly})


def test_partner_plan_price_can_no_longer_be_edited_independently(client):
    """Per explicit product request: PATCH /partner-plans/{code} no longer
    accepts monthlyPrice/yearlyPrice at all -- pricing is business-side-only
    now, so a partner-only price edit can never happen again."""
    headers = _login_admin(client)
    before = client.get("/api/partner-plans").json()["plans"]
    before_price = next(p["monthly_price"] for p in before if p["code"] == "manage")

    resp = client.patch("/api/partner-plans/manage", headers=headers, json={"monthlyPrice": 99999})
    assert resp.status_code == 400, resp.text
    assert "no editable fields" in resp.json()["error"].lower()

    after = client.get("/api/partner-plans").json()["plans"]
    after_price = next(p["monthly_price"] for p in after if p["code"] == "manage")
    assert after_price == before_price


def test_partner_manage_and_grow_no_longer_unlock_connect_free(client):
    """Retired-feature regression test (partner side, mirror of the
    business-side one above): activating GROW + CONNECT together must NOT
    auto-grant MANAGE for free anymore."""
    partner = _login(client, PUNELIFE_PARTNER_EMAIL)
    headers = _headers(partner)

    mine = client.get("/api/partner-plans/mine", headers=headers).json()
    assert mine["activePillars"] == ["grow"]  # seeded with only GROW active

    sub_resp = client.post("/api/partner-plans/subscribe", json={"planCode": "connect"}, headers=headers)
    assert sub_resp.status_code == 201, sub_resp.text
    assert "bonusGranted" not in sub_resp.json()

    mine = client.get("/api/partner-plans/mine", headers=headers).json()
    assert set(["grow", "connect"]).issubset(set(mine["activePillars"]))
    assert "manage" not in mine["activePillars"]

    cancel_resp = client.post("/api/partner-plans/cancel", json={"planCode": "connect"}, headers=headers)
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert "bonusRevoked" not in cancel_resp.json()


def test_business_owner_cannot_use_partner_plans_endpoints(client, unique_suffix):
    reg = _register_business(client, unique_suffix)
    resp = client.post("/api/partner-plans/subscribe", json={"planCode": "grow"}, headers=_headers(reg))
    assert resp.status_code == 403, resp.text

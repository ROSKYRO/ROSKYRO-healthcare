"""Regression tests for round 23 -- self-serve UPI subscription/plan claims
(both the business side, routers/plans.py, and the partner side,
routers/partner_plans.py) no longer activate a pillar instantly. A claim is
created with status "pending_payment"; only a roskyro_admin calling
POST /{id}/confirm-payment flips it to "active" and actually unlocks the
pillar (get_active_pillars / get_active_partner_pillars only ever count
status=="active" rows). POST /{id}/reject-payment closes a bogus claim
without activating it. This mirrors the pending -> self-reported-paid ->
ROSKYRO-confirmed lifecycle subscription_renewals.py already used for every
renewal AFTER the first billing period -- round 23 closes the one gap that
flow's own docstring used to call out deliberately (the very first period
was still instant) per explicit product request.

Internal-staff plan assignment (source: "admin_assigned", via {orgId} in the
body) is NOT put through this gate -- there's no external UPI payment to
verify in that path; the admin action IS the confirmation.
"""
import itertools

DEMO_PASSWORD = "Roskyro@123"
ADMIN_EMAIL = "admin@roskyro.com"
PUNELIFE_PARTNER_EMAIL = "admin.punelife.imaging.centre@example.com"  # partner_admin, seeded with only GROW active
_reg_counter = itertools.count(1)


def _register_business(client, unique_suffix, **overrides):
    n = next(_reg_counter)
    body = {
        "orgName": f"Round23 Test Clinic {unique_suffix}{n}",
        "businessType": "clinic",
        "city": "Pune",
        "ownerName": "Dr. Round23 Test",
        "email": f"round23.test.{unique_suffix}{n}@example.com",
        "phone": f"92{unique_suffix}{n}".rjust(10, "0")[:10],
        "password": DEMO_PASSWORD,
    }
    body.update(overrides)
    resp = client.post("/api/auth/register", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _headers(reg_json):
    return {"Authorization": f"Bearer {reg_json['token']}"}


def _login(client, identifier, password=DEMO_PASSWORD):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# ---------------------------------------------------------------------------
# Business side (routers/plans.py)
# ---------------------------------------------------------------------------

def test_self_serve_subscribe_is_pending_not_active(client, unique_suffix):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)

    resp = client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    assert resp.status_code == 201, resp.text
    sub = resp.json()["subscription"]
    assert sub["status"] == "pending_payment"
    assert sub["started_at"] is None

    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "grow" not in mine["activePillars"]
    # The pending row still shows up in subscription history.
    assert any(s["id"] == sub["id"] and s["status"] == "pending_payment" for s in mine["subscriptions"])


def test_only_admin_can_confirm_or_reject_payment(client, unique_suffix):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)
    resp = client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    sub_id = resp.json()["subscription"]["id"]

    # The owner themself cannot confirm their own payment.
    own_confirm = client.post(f"/api/plans/{sub_id}/confirm-payment", headers=headers)
    assert own_confirm.status_code == 403, own_confirm.text

    own_reject = client.post(f"/api/plans/{sub_id}/reject-payment", headers=headers)
    assert own_reject.status_code == 403, own_reject.text


def test_admin_confirm_activates_the_pillar(client, unique_suffix, admin_headers):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)
    resp = client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    sub_id = resp.json()["subscription"]["id"]

    confirm = client.post(f"/api/plans/{sub_id}/confirm-payment", headers=admin_headers)
    assert confirm.status_code == 200, confirm.text
    confirmed = confirm.json()["subscription"]
    assert confirmed["status"] == "active"
    assert confirmed["started_at"] is not None

    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "grow" in mine["activePillars"]


def test_confirm_payment_is_not_repeatable(client, unique_suffix, admin_headers):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)
    resp = client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    sub_id = resp.json()["subscription"]["id"]

    first = client.post(f"/api/plans/{sub_id}/confirm-payment", headers=admin_headers)
    assert first.status_code == 200, first.text
    second = client.post(f"/api/plans/{sub_id}/confirm-payment", headers=admin_headers)
    assert second.status_code == 400, second.text


def test_confirm_payment_unknown_id_404s(client, admin_headers):
    resp = client.post("/api/plans/does-not-exist-xyz/confirm-payment", headers=admin_headers)
    assert resp.status_code == 404, resp.text


def test_duplicate_pending_claim_for_same_plan_is_refused(client, unique_suffix):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)
    first = client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    assert first.status_code == 201, first.text

    dupe = client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    assert dupe.status_code == 409, dupe.text
    assert "awaiting" in dupe.json()["error"].lower() or "confirmation" in dupe.json()["error"].lower()


def test_reject_payment_leaves_pillar_locked_and_allows_resubmission(client, unique_suffix, admin_headers):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)
    resp = client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    sub_id = resp.json()["subscription"]["id"]

    reject = client.post(f"/api/plans/{sub_id}/reject-payment", headers=admin_headers, json={"reason": "UTR not found"})
    assert reject.status_code == 200, reject.text
    assert reject.json()["subscription"]["status"] == "payment_rejected"

    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "manage" not in mine["activePillars"]

    # A fresh claim for the same plan is allowed after a rejection.
    again = client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    assert again.status_code == 201, again.text

    reject_again_should_fail = client.post(f"/api/plans/{sub_id}/reject-payment", headers=admin_headers)
    assert reject_again_should_fail.status_code == 400, reject_again_should_fail.text


def test_business_can_withdraw_its_own_pending_claim(client, unique_suffix):
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)
    resp = client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    sub_id = resp.json()["subscription"]["id"]

    withdraw = client.post("/api/plans/cancel", json={"planCode": "manage"}, headers=headers)
    assert withdraw.status_code == 200, withdraw.text
    assert withdraw.json()["subscription"]["status"] == "cancelled"
    assert withdraw.json()["subscription"]["id"] == sub_id

    # And can claim it again afterward.
    again = client.post("/api/plans/subscribe", json={"planCode": "manage"}, headers=headers)
    assert again.status_code == 201, again.text


def test_bundle_upgrade_keeps_existing_pillar_active_until_confirmed(client, unique_suffix, admin_headers):
    """The core reason the bundle's cancel-superseded-plans sweep was moved
    from subscribe() to confirm_payment(): a business already paying for an
    individual pillar must not lose it just because it CLAIMED a bundle
    upgrade -- only once ROSKYRO actually confirms the upgrade should the
    old individual plan be superseded."""
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)

    grow = client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    client.post(f"/api/plans/{grow.json()['subscription']['id']}/confirm-payment", headers=admin_headers)
    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "grow" in mine["activePillars"]

    bundle = client.post("/api/plans/subscribe", json={"planCode": "complete", "billingCycle": "monthly"}, headers=headers)
    assert bundle.status_code == 201, bundle.text

    # Bundle claim is still pending -- grow must STILL be active, not cut off.
    mine = client.get("/api/plans/mine", headers=headers).json()
    assert "grow" in mine["activePillars"]
    assert "connect" not in mine["activePillars"]
    grow_row = next(s for s in mine["subscriptions"] if s["plan_code"] == "grow")
    assert grow_row["status"] == "active"

    confirm = client.post(f"/api/plans/{bundle.json()['subscription']['id']}/confirm-payment", headers=admin_headers)
    assert confirm.status_code == 200, confirm.text

    # NOW the bundle is active and the superseded individual "grow" plan is
    # cancelled, but every pillar (via the bundle) is still available.
    mine = client.get("/api/plans/mine", headers=headers).json()
    assert set(mine["activePillars"]) == {"grow", "manage", "connect"}
    grow_row = next(s for s in mine["subscriptions"] if s["plan_code"] == "grow")
    assert grow_row["status"] == "cancelled"


def test_addon_confirm_rechecks_required_pillar_still_active(client, unique_suffix, admin_headers):
    """If the pillar an add-on depends on gets cancelled between the claim
    and the confirmation, confirming the add-on must fail rather than
    silently activating an orphaned add-on."""
    reg = _register_business(client, unique_suffix)
    headers = _headers(reg)

    grow = client.post("/api/plans/subscribe", json={"planCode": "grow"}, headers=headers)
    client.post(f"/api/plans/{grow.json()['subscription']['id']}/confirm-payment", headers=admin_headers)

    reels = client.post("/api/plans/subscribe", json={"planCode": "reels"}, headers=headers)
    assert reels.status_code == 201, reels.text

    # Cancel grow while the reels add-on claim is still pending.
    cancel_resp = client.post("/api/plans/cancel", json={"planCode": "grow"}, headers=headers)
    assert cancel_resp.status_code == 200, cancel_resp.text
    # cascade_cancel_dependent_addons only cascades ACTIVE add-ons, so the
    # still-pending reels claim survives this cancel untouched.

    confirm_reels = client.post(f"/api/plans/{reels.json()['subscription']['id']}/confirm-payment", headers=admin_headers)
    assert confirm_reels.status_code == 400, confirm_reels.text


def test_admin_assigned_plan_is_still_instant(client, unique_suffix, admin_headers):
    """Internal-staff assignment (source: admin_assigned, via {orgId}) is
    NOT put through the pending-confirmation gate -- there's no external UPI
    payment to verify; the admin action itself is the confirmation."""
    reg = _register_business(client, unique_suffix)
    org_id = reg["user"]["orgId"]

    resp = client.post("/api/plans/subscribe", json={"orgId": org_id, "planCode": "manage"}, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    sub = resp.json()["subscription"]
    assert sub["status"] == "active"
    assert sub["started_at"] is not None

    mine = client.get("/api/plans/mine", headers=_headers(reg)).json()
    assert "manage" in mine["activePillars"]


# ---------------------------------------------------------------------------
# Partner side (routers/partner_plans.py) -- same gate, separate collection.
# ---------------------------------------------------------------------------

def test_partner_self_serve_subscribe_is_pending_not_active(client, unique_suffix, admin_headers):
    headers = _login(client, PUNELIFE_PARTNER_EMAIL)
    mine_before = client.get("/api/partner-plans/mine", headers=headers).json()
    assert mine_before["activePillars"] == ["grow"]

    resp = client.post("/api/partner-plans/subscribe", json={"planCode": "connect"}, headers=headers)
    assert resp.status_code == 201, resp.text
    sub = resp.json()["subscription"]
    assert sub["status"] == "pending_payment"

    mine = client.get("/api/partner-plans/mine", headers=headers).json()
    assert "connect" not in mine["activePillars"]

    confirm = client.post(f"/api/partner-plans/{sub['id']}/confirm-payment", headers=admin_headers)
    assert confirm.status_code == 200, confirm.text
    mine = client.get("/api/partner-plans/mine", headers=headers).json()
    assert "connect" in mine["activePillars"]

    # Clean up so this doesn't leave a stray active subscription behind for
    # other tests sharing this seeded partner account.
    client.post("/api/partner-plans/cancel", json={"planCode": "connect"}, headers=headers)


def test_partner_owner_cannot_confirm_own_payment(client, unique_suffix):
    headers = _login(client, PUNELIFE_PARTNER_EMAIL)
    resp = client.post("/api/partner-plans/subscribe", json={"planCode": "manage"}, headers=headers)
    assert resp.status_code == 201, resp.text
    sub_id = resp.json()["subscription"]["id"]

    own_confirm = client.post(f"/api/partner-plans/{sub_id}/confirm-payment", headers=headers)
    assert own_confirm.status_code == 403, own_confirm.text

    # Clean up the pending claim so it doesn't linger for other tests.
    client.post("/api/partner-plans/cancel", json={"planCode": "manage"}, headers=headers)


def test_partner_reject_payment(client, unique_suffix, admin_headers):
    headers = _login(client, PUNELIFE_PARTNER_EMAIL)
    resp = client.post("/api/partner-plans/subscribe", json={"planCode": "manage"}, headers=headers)
    sub_id = resp.json()["subscription"]["id"]

    reject = client.post(f"/api/partner-plans/{sub_id}/reject-payment", headers=admin_headers)
    assert reject.status_code == 200, reject.text
    assert reject.json()["subscription"]["status"] == "payment_rejected"

    mine = client.get("/api/partner-plans/mine", headers=headers).json()
    assert "manage" not in mine["activePillars"]

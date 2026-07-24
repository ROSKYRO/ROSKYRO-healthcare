EXPECTED_CODES = {"grow", "manage", "connect", "complete"}


def test_plans_list_has_code_field(client):
    """Regression test for a real bug found in an earlier round: plan docs
    use their pillar slug ("grow"/"manage"/...) as _id, and the whole
    frontend (PricingCards, Plans.jsx, PricingManagement.jsx) reads
    `plan.code` -- but the generic to_out() helper only renamed _id -> id,
    so `code` was silently missing from every plans response and plan
    activation was broken everywhere. `_plan_out()` in plans.py fixes this
    by mirroring id into code explicitly."""
    resp = client.get("/api/plans")
    assert resp.status_code == 200, resp.text
    plans = resp.json()["plans"]
    assert len(plans) >= 3

    for plan in plans:
        assert "id" in plan and plan["id"]
        assert "code" in plan and plan["code"], f"plan {plan.get('name')} is missing `code`"
        assert plan["code"] == plan["id"]

    codes = {p["code"] for p in plans}
    assert codes & EXPECTED_CODES, f"expected at least one of {EXPECTED_CODES}, got {codes}"

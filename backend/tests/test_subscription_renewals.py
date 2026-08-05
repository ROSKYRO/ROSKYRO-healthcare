"""Tests for the subscription renewal payment lifecycle -- mirrors the
Marketing Fee model's pending -> business self-reports paid -> ROSKYRO
confirms received -> invoice pattern (see test_marketing_fees.py), but for
money flowing the OTHER direction: a business pays ROSKYRO for its own
GROW/MANAGE/CONNECT/Complete subscription renewal, not a
partner paying a per-referral fee.

Deliberately scoped to RENEWALS only -- the very first billing period is
still the existing instant "I've Paid -- Activate" checkout in
routers/plans.py's /subscribe (unchanged), so /subscription-renewals/generate
must never create a charge for a subscription's own start period."""
from datetime import datetime, timezone

from app.routers.subscription_renewals import _is_renewal_period_due

DEMO_PASSWORD = "Roskyro@123"
SUNRISE_EMAIL = "sunrise.family.clinic@example.com"
CITYSCAN_PARTNER_ADMIN_EMAIL = "admin.cityscan.diagnostics@example.com"


def _login(client, identifier):
    resp = client.post("/api/auth/login", json={"identifier": identifier, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _next_period(period: str) -> str:
    year, month = int(period[:4]), int(period[5:7])
    month += 1
    if month > 12:
        month = 1
        year += 1
    return f"{year:04d}-{month:02d}"


# --- _is_renewal_period_due: pure calendar-math unit tests, no DB/API involved ---

def test_monthly_due_check_excludes_start_period_and_earlier():
    started = datetime(2026, 3, 15, tzinfo=timezone.utc)
    assert not _is_renewal_period_due(started, "monthly", "2026-03")  # the subscription's own start period
    assert not _is_renewal_period_due(started, "monthly", "2026-02")  # before start -- shouldn't happen, but must not be "due"


def test_monthly_due_check_due_every_month_after_start():
    started = datetime(2026, 3, 15, tzinfo=timezone.utc)
    assert _is_renewal_period_due(started, "monthly", "2026-04")
    assert _is_renewal_period_due(started, "monthly", "2026-12")
    assert _is_renewal_period_due(started, "monthly", "2027-01")
    assert _is_renewal_period_due(started, "monthly", "2030-06")


def test_yearly_due_check_only_same_calendar_month_next_year_onward():
    started = datetime(2026, 3, 15, tzinfo=timezone.utc)
    assert not _is_renewal_period_due(started, "yearly", "2026-03")  # start period itself
    assert not _is_renewal_period_due(started, "yearly", "2026-04")  # same year, wrong month -- yearly isn't due mid-year
    assert not _is_renewal_period_due(started, "yearly", "2027-04")  # right year, wrong month
    assert _is_renewal_period_due(started, "yearly", "2027-03")  # exactly one year later, same month
    assert _is_renewal_period_due(started, "yearly", "2028-03")  # two years later, same month


# --- Generation: idempotent, skips the start period, permission-gated ---

def test_generate_skips_the_subscriptions_own_start_period(client, admin_headers):
    start_period = datetime.now(timezone.utc).strftime("%Y-%m")
    resp = client.post("/api/subscription-renewals/generate", headers=admin_headers, json={"period": start_period})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["created"] == 0, "no charge should ever be generated for a subscription's own activation period"


def test_generate_is_admin_only_and_idempotent(client, admin_headers):
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    start_period = datetime.now(timezone.utc).strftime("%Y-%m")
    due_period = _next_period(start_period)

    forbidden = client.post("/api/subscription-renewals/generate", headers=sunrise_headers, json={"period": due_period})
    assert forbidden.status_code == 403, forbidden.text

    first = client.post("/api/subscription-renewals/generate", headers=admin_headers, json={"period": due_period})
    assert first.status_code == 201, first.text
    assert first.json()["created"] > 0, "expected at least the seeded active subscriptions to be due this period"

    second = client.post("/api/subscription-renewals/generate", headers=admin_headers, json={"period": due_period})
    assert second.status_code == 201, second.text
    assert second.json()["created"] == 0, "re-running for the same period must not create duplicates"
    assert second.json()["skipped"] == first.json()["created"]


def test_partner_cannot_list_subscription_renewals(client):
    partner_headers = _login(client, CITYSCAN_PARTNER_ADMIN_EMAIL)
    resp = client.get("/api/subscription-renewals", headers=partner_headers)
    assert resp.status_code == 403, resp.text


def test_business_only_sees_its_own_renewal_charges(client, admin_headers):
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    start_period = datetime.now(timezone.utc).strftime("%Y-%m")
    due_period = _next_period(start_period)
    client.post("/api/subscription-renewals/generate", headers=admin_headers, json={"period": due_period})

    admin_view = client.get("/api/subscription-renewals", headers=admin_headers, params={"period": due_period})
    assert admin_view.status_code == 200, admin_view.text
    all_org_ids = {r["org_id"] for r in admin_view.json()["renewals"]}
    assert len(all_org_ids) > 1, "expected renewal charges for more than one business this period"

    sunrise_view = client.get("/api/subscription-renewals", headers=sunrise_headers, params={"period": due_period})
    assert sunrise_view.status_code == 200, sunrise_view.text
    rows = sunrise_view.json()["renewals"]
    assert len(rows) >= 1
    assert all(r["org_name"] == "Sunrise Family Clinic" for r in rows)


# --- Full two-sided lifecycle: mark-paid -> confirm-received -> invoice ---

def test_full_mark_paid_confirm_invoice_lifecycle(client, admin_headers):
    sunrise_headers = _login(client, SUNRISE_EMAIL)
    start_period = datetime.now(timezone.utc).strftime("%Y-%m")
    # use a period two months out so this test owns a charge no earlier test
    # in this file has already touched (test_business_only_sees_its_own_
    # renewal_charges already fully generated+left-pending the +1 period)
    lifecycle_period = _next_period(_next_period(start_period))
    gen = client.post("/api/subscription-renewals/generate", headers=admin_headers, json={"period": lifecycle_period})
    assert gen.status_code == 201, gen.text

    rows = client.get("/api/subscription-renewals", headers=sunrise_headers, params={"period": lifecycle_period}).json()["renewals"]
    assert len(rows) == 1, "Sunrise has exactly one active subscription"
    charge = rows[0]
    assert charge["status"] == "pending"
    assert charge["payer_marked_paid_at"] is None

    # the ROSKYRO team cannot mark it paid as a plain "self-report" before
    # the business has claimed anything -- their POST here IS the dispute-
    # resolution override and finalizes immediately, so instead exercise the
    # normal two-sided path: business claims, then admin confirms.
    partner_headers = _login(client, CITYSCAN_PARTNER_ADMIN_EMAIL)  # not the payer for this charge
    forbidden = client.post(f"/api/subscription-renewals/{charge['id']}/mark-paid", headers=partner_headers, json={})
    assert forbidden.status_code == 403, forbidden.text

    marked = client.post(f"/api/subscription-renewals/{charge['id']}/mark-paid", headers=sunrise_headers, json={"paymentReference": "UPI-PYTEST-1"})
    assert marked.status_code == 200, marked.text
    assert marked.json()["renewal"]["status"] == "pending"
    assert marked.json()["renewal"]["payer_marked_paid_at"]
    assert marked.json()["renewal"]["payment_reference"] == "UPI-PYTEST-1"

    # marking paid a second time is rejected -- already awaiting confirmation
    dup = client.post(f"/api/subscription-renewals/{charge['id']}/mark-paid", headers=sunrise_headers, json={})
    assert dup.status_code == 400, dup.text

    # only ROSKYRO internal can confirm receipt -- the business itself cannot
    forbidden_confirm = client.post(f"/api/subscription-renewals/{charge['id']}/confirm-received", headers=sunrise_headers)
    assert forbidden_confirm.status_code == 403, forbidden_confirm.text

    confirmed = client.post(f"/api/subscription-renewals/{charge['id']}/confirm-received", headers=admin_headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["renewal"]["status"] == "paid"
    assert confirmed.json()["renewal"]["paid_at"]

    # confirming twice is rejected
    dup_confirm = client.post(f"/api/subscription-renewals/{charge['id']}/confirm-received", headers=admin_headers)
    assert dup_confirm.status_code == 400, dup_confirm.text

    # both the business and ROSKYRO internal can download the finalized invoice
    invoice = client.get(f"/api/subscription-renewals/{charge['id']}/invoice", headers=sunrise_headers)
    assert invoice.status_code == 200, invoice.text
    assert invoice.headers["content-type"] == "application/pdf"
    assert invoice.content[:5] == b"%PDF-"

    invoice_internal = client.get(f"/api/subscription-renewals/{charge['id']}/invoice", headers=admin_headers)
    assert invoice_internal.status_code == 200, invoice_internal.text

    # a different business cannot download this one's invoice
    other_business_headers = _login(client, "smile.bright.dental@example.com")
    forbidden_invoice = client.get(f"/api/subscription-renewals/{charge['id']}/invoice", headers=other_business_headers)
    assert forbidden_invoice.status_code == 403, forbidden_invoice.text


def test_internal_override_mark_paid_finalizes_immediately(client, admin_headers):
    """ROSKYRO internal's own mark-paid call (not the business's) is a
    dispute-resolution override -- it finalizes the charge to "paid"
    immediately, bypassing the normal two-sided confirm step."""
    start_period = datetime.now(timezone.utc).strftime("%Y-%m")
    override_period = _next_period(_next_period(_next_period(start_period)))
    gen = client.post("/api/subscription-renewals/generate", headers=admin_headers, json={"period": override_period})
    assert gen.status_code == 201, gen.text

    sunrise_headers = _login(client, SUNRISE_EMAIL)
    rows = client.get("/api/subscription-renewals", headers=sunrise_headers, params={"period": override_period}).json()["renewals"]
    charge = rows[0]

    override = client.post(f"/api/subscription-renewals/{charge['id']}/mark-paid", headers=admin_headers, json={"paymentReference": "OVERRIDE-1"})
    assert override.status_code == 200, override.text
    assert override.json()["renewal"]["status"] == "paid"
    assert override.json()["renewal"]["confirmed_by"] == "internal_override"

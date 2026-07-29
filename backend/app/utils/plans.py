from datetime import timedelta
from fastapi import Depends, HTTPException

from app.auth import get_current_user
from app.utils.pillars import PILLAR_CODES, get_active_pillars  # re-exported
from app.utils.ids import now, as_aware

__all__ = ["PILLAR_CODES", "get_active_pillars", "require_plan", "next_renewal_date", "add_cycle"]


def add_cycle(d, billing_cycle: str, anchor_day: int | None = None):
    """Advance a datetime by one billing cycle ('monthly' or 'yearly'),
    clamping to the last valid day of the target month (e.g. Jan 31 + 1
    month -> Feb 28/29, not an invalid Feb 31). Shared by
    next_renewal_date() below and routers/subscription_renewals.py's
    renewal-due calendar math, so both agree on exactly what "one cycle
    later" means for a given subscription.

    anchor_day is the subscription's ORIGINAL billing day-of-month. Fixed
    bug: when this is stepped repeatedly (as next_renewal_date does, walking
    forward one cycle at a time until it passes today), clamping against the
    PREVIOUS clamped result compounds and the billing day drifts permanently
    earlier -- a business that signed up on Jan 31 got clamped to Feb 28,
    then every later month anchored on 28, so its August renewal showed as
    Aug 28 instead of Aug 31. Anchoring each step to the original day makes
    February a one-off clamp rather than a permanent one.
    """
    import calendar
    day = anchor_day or d.day
    if billing_cycle == "yearly":
        year = d.year + 1
        last_day = calendar.monthrange(year, d.month)[1]
        return d.replace(year=year, day=min(day, last_day))
    # monthly
    month = d.month + 1
    year = d.year + (1 if month > 12 else 0)
    month = 1 if month > 12 else month
    last_day = calendar.monthrange(year, month)[1]
    return d.replace(year=year, month=month, day=min(day, last_day))


def require_plan(pillar: str):
    """Dependency factory — port of requirePlan(pillar) middleware. Blocks
    customer-shell users who lack the given pillar subscription. Partner
    and internal users are never gated: pillars are a customer (healthcare
    business) commercial construct."""

    async def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["appShell"] != "customer":
            return current_user
        pillars = current_user.get("activePillars") or await get_active_pillars(current_user["orgId"])
        if pillar not in pillars:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": f"This feature is part of the ROSKYRO {pillar.upper()} pillar, which isn't active on your plan yet.",
                    "requiredPillar": pillar,
                    "upgradeRequired": True,
                },
            )
        return current_user

    return dependency


def next_renewal_date(started_at, billing_cycle: str):
    """Given when a subscription started and its billing cycle, compute the
    next upcoming renewal date — started_at plus whole cycles until the
    result is in the future. There's no auto-renew job in this build (v1
    scope), so this is "when this subscription is next due." Direct port
    of server/src/utils/plans.js's nextRenewalDate."""
    if not started_at:
        return None
    started_at = as_aware(started_at)

    current = now()
    renewal = started_at
    # anchor_day pins every step to the ORIGINAL billing day-of-month, so a
    # short month clamps once instead of permanently pulling the billing day
    # earlier for every month after it. See add_cycle's note.
    anchor_day = started_at.day
    for _ in range(1000):
        if renewal > current:
            break
        renewal = add_cycle(renewal, billing_cycle, anchor_day=anchor_day)
    return renewal

from datetime import timedelta
from fastapi import Depends, HTTPException

from app.auth import get_current_user
from app.utils.pillars import PILLAR_CODES, get_active_pillars  # re-exported
from app.utils.ids import now, as_aware

__all__ = ["PILLAR_CODES", "get_active_pillars", "require_plan", "next_renewal_date"]


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

    def add_cycle(d):
        if billing_cycle == "yearly":
            try:
                return d.replace(year=d.year + 1)
            except ValueError:
                # Feb 29 on a non-leap year landing spot
                return d.replace(month=3, day=1, year=d.year + 1)
        # monthly
        month = d.month + 1
        year = d.year + (1 if month > 12 else 0)
        month = 1 if month > 12 else month
        day = d.day
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        return d.replace(year=year, month=month, day=min(day, last_day))

    current = now()
    renewal = started_at
    for _ in range(1000):
        if renewal > current:
            break
        renewal = add_cycle(renewal)
    return renewal

from datetime import datetime, timedelta

# Helpers for the QR self-booking feature (MANAGE pillar). Direct port of
# server/src/utils/booking.js, extended for multi-doctor/faculty
# scheduling: a multispeciality clinic or hospital has different doctors
# available on different days/times, so slot generation now resolves a
# specific doctor's *weekly recurring schedule* for a given calendar date,
# rather than one fixed open/close window for the whole org.

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def time_to_minutes(t: str) -> int:
    """Accepts 'HH:MM' or 'HH:MM:SS'."""
    parts = str(t).split(":")
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_time(mins: int) -> str:
    h = mins // 60
    m = mins % 60
    return f"{h:02d}:{m:02d}"


def generate_slots(open_time: str, close_time: str, duration_minutes: int = 30) -> list[str]:
    """Build the list of slot start-times ('HH:MM') between open and close
    time, stepped by duration_minutes. The close time is treated as the
    last moment a slot may *start* before -- slots that would run past
    closing are not offered."""
    open_min = time_to_minutes(open_time)
    close_min = time_to_minutes(close_time)
    duration = int(duration_minutes or 30)
    slots = []
    t = open_min
    while t + duration <= close_min:
        slots.append(minutes_to_time(t))
        t += duration
    return slots


def upcoming_dates(window_days: int) -> list[str]:
    """Today (+0) through window_days-1 ahead, as 'YYYY-MM-DD' strings."""
    today = datetime.utcnow().date()
    return [(today + timedelta(days=i)).isoformat() for i in range(int(window_days))]


def day_key_for_date(date_str: str) -> str:
    """'YYYY-MM-DD' -> 'mon'..'sun'."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    return DAY_KEYS[d.weekday()]


def doctor_slots_for_date(doctor: dict, date_str: str) -> list[str]:
    """A doctor's slot start-times for one specific calendar date, resolved
    from their weekly recurring schedule -- empty if that doctor simply
    doesn't work that day of the week at all (e.g. a doctor who only sees
    patients Mon/Wed/Fri has no slots on a Tuesday)."""
    day = day_key_for_date(date_str)
    entry = next((e for e in (doctor.get("weekly_schedule") or []) if e.get("day") == day), None)
    if not entry:
        return []
    return generate_slots(entry["open_time"], entry["close_time"], doctor.get("slot_duration_minutes") or 30)

from datetime import datetime, timedelta, timezone

# Helpers for the QR self-booking feature (MANAGE pillar). Direct port of
# server/src/utils/booking.js, extended for multi-doctor/faculty
# scheduling: a multispeciality clinic or hospital has different doctors
# available on different days/times, so slot generation now resolves a
# specific doctor's *weekly recurring schedule* for a given calendar date,
# rather than one fixed open/close window for the whole org.

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# This app is India-only (INR pricing, en-IN locale, "Mon-Sat 9AM-7PM IST"
# on every public-facing page) -- IST is a fixed +5:30 offset, no DST, so a
# plain timedelta is enough (no pytz/zoneinfo dependency needed).
IST_OFFSET = timedelta(hours=5, minutes=30)

# Matches the max="60" the Booking Settings form already enforces in the UI.
MAX_BOOKING_WINDOW_DAYS = 60


def ist_day_start(moment: datetime | None = None) -> datetime:
    """The instant at which the clinic's *IST* calendar day began, returned
    in the same UTC timezone the app stores timestamps in.

    Timestamps here are stored as timezone-aware UTC (utils/ids.py's now()),
    so any "since midnight today" query has to compare against IST midnight
    *expressed in UTC* -- which is 18:30 UTC on the previous calendar date,
    not 00:00 UTC. Using plain UTC midnight rolls the day over at 05:30 IST
    instead, i.e. in the middle of an IST morning shift.
    """
    base = moment or datetime.now(timezone.utc)
    ist_midnight = (base + IST_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0)
    return ist_midnight - IST_OFFSET


def ist_date_str(moment: datetime | None = None) -> str:
    """The clinic's current IST calendar date as 'YYYY-MM-DD'."""
    base = moment or datetime.now(timezone.utc)
    return (base + IST_OFFSET).date().isoformat()


def time_to_minutes(t: str) -> int:
    """Accepts 'HH:MM' or 'HH:MM:SS'. Returns None for anything else.

    Hardened: this used to do a bare int(parts[0]) * 60 + int(parts[1]) on
    whatever string it was handed. routers/doctors.py now rejects a
    malformed time at the write, but rows saved BEFORE that validation
    existed are still sitting in the production database -- and the two
    callers of this function are on the public, unauthenticated patient
    booking path, where an IndexError/ValueError becomes a raw 500 for every
    patient of that business. Returning None lets doctor_slots_for_date()
    skip an unusable schedule entry instead of taking the page down.
    """
    parts = str(t).split(":")
    if len(parts) < 2:
        return None
    try:
        hours, minutes = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


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
    # An unparseable open/close time yields no slots rather than a 500 --
    # see time_to_minutes' own note about pre-validation rows in production.
    if open_min is None or close_min is None or open_min >= close_min:
        return []
    try:
        duration = int(duration_minutes or 30)
    except (TypeError, ValueError):
        duration = 30
    # Hardened against a non-positive duration. routers/doctors.py now
    # refuses to store one, but a doctor row written before that validation
    # existed can still hold e.g. -5 -- and with a negative (or zero) step
    # the loop below never terminates: `t` moves away from `close_min`
    # instead of toward it, and minutes_to_time(-10) returns "-1:50" rather
    # than raising, so there is nothing to break the cycle. Both callers
    # (public availability + public book) are unauthenticated, so that was
    # an unbounded CPU+memory loop inside an async handler -- it blocks the
    # event loop for EVERY tenant on the worker, not just this business.
    if duration < 1:
        duration = 30
    slots = []
    t = open_min
    while t + duration <= close_min:
        slots.append(minutes_to_time(t))
        t += duration
    return slots


def upcoming_dates(window_days: int) -> list[str]:
    """Today (+0) through window_days-1 ahead, as 'YYYY-MM-DD' strings.

    Fixed: this used to compute "today" as datetime.utcnow().date() --
    plain UTC, not the clinic's actual local day. For roughly the first
    5.5 hours of every IST calendar day (00:00-05:29 IST, i.e. while it's
    still the previous day in UTC), that made this function think "today"
    was still YESTERDAY. Two real, public-facing endpoints depend on this
    exact value at the exact same moment (public_booking.py's
    get_doctor_availability building the calendar AND book_slot
    re-validating the submitted date against it) -- so a patient booking
    during that window could see, and successfully submit, a date that had
    already closed out operationally for the clinic, with no error at any
    step. Now computed against the clinic's IST wall-clock day instead.
    """
    today = (datetime.utcnow() + IST_OFFSET).date()
    # Clamped to the same 1..60 range the Booking Settings form already
    # enforces client-side (BookingSettings.jsx's min="1" max="60"). The
    # server-side PATCH validator only enforced a floor of 1, so an API
    # client could store bookingWindowDays: 100000 and make the public
    # availability endpoint build 100,000 date entries -- each with a full
    # slot list -- on every unauthenticated request.
    try:
        days = int(window_days)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, MAX_BOOKING_WINDOW_DAYS))
    return [(today + timedelta(days=i)).isoformat() for i in range(days)]


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

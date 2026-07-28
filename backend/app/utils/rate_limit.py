"""Minimal in-process rate limiter for the handful of UNAUTHENTICATED,
DB-writing public endpoints (self-booking, contact form, newsletter
signup) -- these have no login wall at all, so with zero throttling a
script can hammer them without limit. That's not just a nuisance: each
public_booking.py `book_slot` call consumes a slot in a real doctor's
daily capacity via an atomic counter (see app/utils/counters.py), so
unthrottled spam can permanently exhaust a clinic's real booking capacity
for actual patients -- a functional denial-of-service, not just junk data.

This is deliberately a simple in-memory sliding window, not a full
rate-limiting library or Redis-backed store -- consistent with this
codebase's existing scope (no billing gateway, no background job
scheduler, no external services beyond Mongo). It only protects a single
process; a multi-worker/multi-instance deployment would need a shared
store (Redis, or Mongo itself) instead. That's a real limitation worth
flagging if this app is ever deployed with more than one process, but for
this build it's a strict improvement over the previous zero-throttling
state.
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

# bucket_name -> ip -> deque of request timestamps within the current window
_REQUESTS: dict[str, dict[str, deque]] = defaultdict(lambda: defaultdict(deque))

# (max requests, window seconds) per named bucket -- generous enough that a
# real patient/visitor never notices, tight enough to stop a scripted loop.
_LIMITS = {
    "public_booking": (10, 60),
    "public_contact": (5, 60),
    "public_newsletter": (5, 60),
    # Fixed: POST /api/auth/login had no throttling at all -- unlimited
    # password guesses per IP against a healthcare SaaS login endpoint with
    # no lockout/backoff/429. Deliberately keyed to only FAILED login
    # attempts (see auth.py's login()), not every call to the endpoint --
    # so this only ever throttles actual wrong-identifier/wrong-password
    # guessing, never legitimate successful logins no matter how frequent
    # (several staff behind one shared clinic IP, or this app's own test
    # suite, which logs in dozens of times per run with valid credentials).
    "auth_login_failed": (10, 60),
}


def enforce_rate_limit(bucket: str, client_ip: str) -> None:
    """Raise HTTP 429 if `client_ip` has exceeded the bucket's limit within
    its rolling window; otherwise records this request and returns."""
    max_requests, window_seconds = _LIMITS.get(bucket, (20, 60))
    now = time.monotonic()
    timestamps = _REQUESTS[bucket][client_ip]

    while timestamps and now - timestamps[0] > window_seconds:
        timestamps.popleft()

    if len(timestamps) >= max_requests:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait a moment and try again.",
        )
    timestamps.append(now)

"""Atomic, race-safe sequence numbers for human-facing sequential IDs
(referral codes, invoice numbers) -- backed by a single small document per
sequence (see app/db.py's `sequence_counters`) and MongoDB's atomic $inc,
the exact same pattern routers/public_booking.py already uses for
QR-booking slot capacity and token numbering (see its `booking_counters`).

Why this replaces `collection.count_documents({})`: counting the WHOLE
target collection to pick "next number" does two things wrong as data
grows --

1. It's an O(collection size) scan on every single write, so referral/
   invoice creation gets slower the more historical volume there is, not
   just under more concurrent load. subscription_renewals.py's bulk
   "Generate Renewal Charges" made this worse still by calling it once per
   active subscription inside a loop.
2. It isn't safe under concurrent requests -- two referrals created in the
   same instant can both read the same count and mint the same code.

A `$inc` on a tiny single-document counter is O(1) regardless of how much
historical data exists, and MongoDB guarantees each concurrent $inc gets
its own unique result, so two concurrent callers can never collide.

Migration safety: a system that's been running on the old
`count_documents({})` scheme already has real codes/invoice numbers out
there matching that count. Switching a sequence straight to a fresh
counter starting at 1 would immediately re-mint codes that already exist
(e.g. RSK-REF-000001, already used by the very first seeded/real
referral). `next_sequence`'s optional `bootstrap` callback solves this: the
FIRST time a given counter is used, if its document doesn't exist yet, it
is seeded (once, atomically, race-safe against concurrent first-callers
via $setOnInsert + upsert) with whatever `bootstrap()` returns -- pass
`collection.count_documents({})` there and the very next call reproduces
exactly the number the old code would have produced, with every call after
that being a pure O(1) increment. The one-time bootstrap scan happens at
most once per sequence, ever, not once per write."""
from pymongo import ReturnDocument

from app.db import sequence_counters


async def next_sequence(counter_id: str, bootstrap=None) -> int:
    """Atomically returns the next integer in the named sequence.

    `counter_id` names the sequence (e.g. "referral_code",
    "billing_invoice_number") -- each distinct id gets its own independent,
    forever-increasing counter document.

    `bootstrap`, if given, is an async zero-arg callable returning the
    integer to seed the counter with the first time it's ever used (see
    module docstring) -- e.g. `lambda: referrals.count_documents({})`. Only
    ever runs once per counter_id (subsequent calls find the counter
    document already exists and skip straight to the atomic increment).
    Omit it for a brand-new sequence with no prior history to continue
    from -- it will simply start at 1.
    """
    if bootstrap is not None:
        existing = await sequence_counters.find_one({"_id": counter_id})
        if existing is None:
            initial = await bootstrap()
            # $setOnInsert + upsert is itself atomic: if two callers race
            # here at the very first use, only one of them actually inserts
            # the document (with value=initial) -- the other's upsert finds
            # it already exists and becomes a no-op, so the counter is
            # never seeded twice or to two different values.
            await sequence_counters.update_one(
                {"_id": counter_id}, {"$setOnInsert": {"value": initial}}, upsert=True,
            )

    doc = await sequence_counters.find_one_and_update(
        {"_id": counter_id}, {"$inc": {"value": 1}}, upsert=True, return_document=ReturnDocument.AFTER,
    )
    return doc["value"]

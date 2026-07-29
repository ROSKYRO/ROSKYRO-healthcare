"""Shared subscription-integrity helper used by both the business catalog
(routers/plans.py) and the partner catalog (routers/partner_plans.py).

Both subscribe endpoints follow a check-then-insert pattern: look for an
existing active row with the same plan_code, 409 if found, otherwise insert.
That is a textbook TOCTOU race. Two requests that arrive at the same instant
-- an impatient double-click on "Activate", or a mobile client retrying a
request that had actually already succeeded -- both run the find_one before
either runs the insert, both find nothing, and both insert. The business
ends up with two active rows for the same plan and is billed twice every
renewal period, with nothing in the UI showing anything wrong.

The obvious fix, a unique index on (org_id, plan_code, status), is NOT safe
to apply here: this ships against a database that is already live, and if
any duplicate rows already exist the index build fails outright at startup
(and, worse, a plain unique index would also collide with the perfectly
legitimate case of one cancelled row plus one active row for the same plan).

So instead this does a deterministic compare-and-repair immediately after
the insert. Both racing requests see the same set of duplicate rows and both
independently pick the SAME winner -- the row with the earliest
(started_at, _id), a total ordering every caller agrees on -- so exactly one
row survives and every loser removes only its own document. There is no
outcome where both delete and the org ends up with nothing.
"""


async def enforce_single_active(collection, org_id: str, plan_code: str, doc_id: str) -> bool:
    """Call immediately AFTER inserting doc_id. Returns True if this document
    is the surviving row, False if it was a duplicate created by a racing
    request (in which case it has already been removed and the caller should
    respond as if the plan was already active)."""
    rows = await collection.find(
        {"org_id": org_id, "plan_code": plan_code, "status": "active"}
    ).to_list(None)
    if len(rows) <= 1:
        return True

    def _sort_key(row):
        # started_at is always set by both callers; the _id tiebreak makes
        # the ordering total even if two rows share a timestamp.
        return (row.get("started_at"), str(row.get("_id")))

    winner = min(rows, key=_sort_key)
    if winner["_id"] == doc_id:
        return True
    await collection.delete_one({"_id": doc_id})
    return False

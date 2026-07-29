"""Patient identity -- one stable `patient_id`, resolved by phone number.

WHY THIS MODULE EXISTS
----------------------
Every patient-linked record in the product (appointments, follow-ups,
invoices, WhatsApp messages, queue entries) used to carry ONLY a
`patient_name` string, and routers/patients.py built a patient's entire
timeline by querying those collections for that NAME:

    appointments.find({"org_id": ..., "patient_name": p["name"]})

So two different people called "Ramesh Kumar" at the same clinic shared a
single medical history: each one's appointments, each one's invoices and
each one's follow-ups showed up on the other's record. In a healthcare
product that is not a cosmetic bug -- it is the wrong person's clinical
history on screen while a doctor is deciding what to do next. "Sharma"
and "Patel" are common enough that this was a matter of when, not if.

The fix is the boring, correct one: give every patient-linked row a
`patient_id` that points at a row in `patients`, and join on THAT.


HOW IDENTITY IS DECIDED
-----------------------
Phone number is the identity key, not the name. In Indian healthcare the
mobile number is what a front desk always asks for, it is what the
patient actually remembers, and unlike a name it is unique per person.
normalize_phone() (utils/phone.py) already collapses every way a number
can be typed -- "+91-98000 00001", "098000 00001", "9800000001" -- down
to the same 10 digits, so the same human always lands on the same record
regardless of who typed it or how.

  * phone present  -> identity is (phone + name) TOGETHER, not phone
                      alone. Phone alone would be wrong in the most
                      ordinary Indian case there is: a family sharing one
                      mobile number. A mother booking for herself and for
                      her child submits the same number twice, and
                      keying on the number alone would fuse the child's
                      clinical history into the mother's -- the same bug,
                      just arrived at from the other direction. Name
                      alone is ambiguous, phone alone over-merges; the
                      pair is exact in practice.
  * phone absent   -> match by name ONLY when exactly one patient in that
                      org carries the name. If two already share it, we
                      deliberately refuse to guess and return None: the
                      row stays unlinked rather than being attached to
                      possibly-the-wrong-person. Unlinked is recoverable
                      later (add the phone, re-run the backfill);
                      wrongly-linked clinical history is not.

Where this errs, it errs toward SPLITTING (one human ends up with two
records because their name was typed two different ways) rather than
MERGING. That direction is deliberate: a split record is visible, and a
human can merge it. A merged record silently shows a doctor the wrong
person's history and nothing on screen says so.

BACKWARD COMPATIBILITY
----------------------
Rows written before this existed have no `patient_id` at all, and patient
documents written before this have no `phone_key`/`name_key`. Both are
handled without a forced migration:

  * linked_history_filter() below matches `patient_id` for new rows and
    STILL falls back to the old name match for rows that have no
    patient_id -- so no business loses history the day this ships.
  * resolve_patient_id() falls back to matching the raw `phone`/`name`
    fields when the *_key lookup misses, and stamps the keys onto that
    document as it goes, so legacy patients self-heal on first touch.

POST /api/patients/link-history (routers/patients.py) does the same job
in bulk and eliminates the name fallback entirely for a business that
runs it.
"""

import re

from app.db import patients
from app.utils.ids import new_id, now
from app.utils.phone import normalize_phone


def phone_key(raw: str | None) -> str | None:
    """The normalized phone we actually key patients on, or None when the
    input is too weak to identify anyone. Anything shorter than a full
    10-digit mobile ("9800", an extension, a blank) must NOT become an
    identity key -- it would collide two unrelated patients, which is the
    exact failure this module exists to prevent."""
    digits = normalize_phone(raw)
    return digits if len(digits) == 10 else None


def name_key(raw: str | None) -> str | None:
    """Case- and whitespace-insensitive form of a patient name, used only
    as the weak fallback key when there is no phone number. casefold()
    (not lower()) because it is the correct Unicode-aware fold, and the
    whitespace collapse means "Ramesh  Kumar" and "ramesh kumar" don't
    silently become two different people."""
    cleaned = re.sub(r"\s+", " ", (raw or "").strip())
    return cleaned.casefold() or None


def _legacy_phone_variants(pk: str) -> list:
    """The literal strings a legacy `patients.phone` value could hold for
    the same human, so a pre-round-19 patient document (which has no
    phone_key) is still found by an exact indexed match instead of a
    collection scan or an unanchored regex."""
    return [pk, f"0{pk}", f"91{pk}", f"+91{pk}", f"+91-{pk}", f"+91 {pk}"]


async def resolve_patient_id(
    org_id: str, name: str | None, phone: str | None = None, *, create: bool = True
) -> str | None:
    """Return the `patients._id` this (name, phone) belongs to for this
    org, creating the patient record when there isn't one yet.

    Returns None -- meaning "write the row without a patient_id" -- when
    identity genuinely can't be established (no usable name, or an
    ambiguous name with no phone). Callers must treat None as normal, not
    as an error: an unlinked row behaves exactly the way every row behaved
    before this module existed.

    This never raises on bad input. It sits in the middle of booking and
    billing write paths, and no identity-bookkeeping problem is worth
    failing a patient's actual appointment over.
    """
    if not org_id:
        return None
    nk = name_key(name)
    if not nk:
        return None
    pk = phone_key(phone)

    if pk:
        existing = await patients.find_one({"org_id": org_id, "phone_key": pk, "name_key": nk})
        if existing:
            return existing["_id"]
        # Legacy patient row: created before phone_key/name_key existed.
        # Match it on the raw fields, then stamp the keys on so this is the
        # last time it costs an extra lookup.
        for row in await patients.find(
            {"org_id": org_id, "phone": {"$in": _legacy_phone_variants(pk)}, "phone_key": None}
        ).limit(20).to_list(None):
            if name_key(row.get("name")) == nk:
                await patients.update_one(
                    {"_id": row["_id"]}, {"$set": {"phone_key": pk, "name_key": nk}}
                )
                return row["_id"]
    else:
        # No phone: only safe when the name is unambiguous within this org.
        # limit(2) is the whole point -- we need to know "is there more than
        # one", not to fetch them all.
        matches = await patients.find(
            {"org_id": org_id, "$or": [{"name_key": nk}, {"name_key": None, "name": name}]}
        ).limit(2).to_list(None)
        if len(matches) > 1:
            return None
        if matches:
            hit = matches[0]
            if hit.get("name_key") is None:
                await patients.update_one({"_id": hit["_id"]}, {"$set": {"name_key": nk}})
            return hit["_id"]

    if not create:
        return None

    doc = {
        "_id": new_id(), "org_id": org_id, "name": (name or "").strip(),
        "phone": phone or None, "phone_key": pk, "name_key": nk,
        "email": None, "age": None, "gender": None, "tags": None, "notes": None,
        "last_visit_at": None, "total_visits": 0, "lifetime_value": 0,
        "created_at": now(), "updated_at": now(),
    }
    await patients.insert_one(doc)
    return doc["_id"]


async def safe_resolve_patient_id(
    org_id: str, name: str | None, phone: str | None = None, *, create: bool = True
) -> str | None:
    """resolve_patient_id() with a blanket except. Used on the write paths
    that must never fail for a reason the patient standing at the desk
    would find absurd -- a QR booking, an invoice, a queue check-in. If
    identity resolution breaks for any reason at all, the row is simply
    written unlinked (exactly the pre-round-19 behaviour) and the real
    operation still succeeds."""
    try:
        return await resolve_patient_id(org_id, name, phone, create=create)
    except Exception:
        return None


def linked_history_filter(patient: dict) -> dict:
    """Mongo filter matching every row belonging to this patient.

    Two arms, on purpose:

      1. patient_id == this patient  -- everything written since round 19,
         exact, immune to same-name collisions.
      2. patient_id missing/null AND patient_name == this name -- the
         legacy rows. These still carry the old same-name ambiguity
         (nothing can retroactively tell two identically-named patients
         apart in data that never recorded which was which), but they are
         a shrinking, fixed set, and POST /api/patients/link-history
         converts them into arm 1 wherever the phone number makes the
         answer unambiguous.

    Note arm 2 requires patient_id to be absent -- so once a row IS
    linked, a different same-name patient can never pull it back in.
    """
    return {
        "org_id": patient["org_id"],
        "$or": [
            {"patient_id": patient["_id"]},
            {"patient_id": None, "patient_name": patient.get("name")},
        ],
    }

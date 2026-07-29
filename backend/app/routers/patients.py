import asyncio
import re

from fastapi import APIRouter, HTTPException, Depends

from app.db import patients, appointments, patient_followups, invoices, whatsapp_messages, queue_entries
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.patients import linked_history_filter, name_key, phone_key, resolve_patient_id

router = APIRouter(
    prefix="/api/patients", tags=["patients"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


@router.get("")
@router.get("/")
async def list_patients(orgId: str | None = None, q: str | None = None, current_user: dict = Depends(get_current_user)):
    # Fixed IDOR: this previously fell through to `else orgId` for ANY
    # non-customer shell, so a partner account (a normal, self-registerable
    # account type -- not just internal) could pass an arbitrary ?orgId=
    # and read another business's entire patient roster, including
    # clinical notes -- same bug class already fixed on appointments.py/
    # billing.py/followups.py/queue.py/reviews.py/reports.py/approvals.py.
    if current_user["appShell"] == "customer":
        org_id = current_user["orgId"]
    elif current_user["appShell"] == "internal" and orgId:
        org_id = orgId
    else:
        raise HTTPException(status_code=400, detail="orgId is required.")

    filt: dict = {"org_id": org_id}
    if q:
        # re.escape: `q` is a raw front-desk-typed search box value used
        # directly as a Mongo regex -- a patient name/phone search
        # containing regex metacharacters ("Mr. (Retd.) Sharma", a phone
        # entered with brackets) would otherwise crash this endpoint with
        # an unhandled re.error instead of just matching that literal text.
        needle = re.escape(q)
        filt["$or"] = [
            {"name": {"$regex": needle, "$options": "i"}},
            {"phone": {"$regex": needle, "$options": "i"}},
        ]
    rows = await patients.find(filt).sort("updated_at", -1).limit(300).to_list(None)
    return {"patients": to_out_many(rows)}


@router.get("/{patient_id}")
async def get_patient(patient_id: str, current_user: dict = Depends(get_current_user)):
    p = await patients.find_one({"_id": patient_id})
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found.")
    # Fixed IDOR: this only ever rejected a MISMATCHED customer -- a partner
    # account (never checked at all) could fetch any patient_id and get
    # that patient's full record plus appointments/follow-ups/invoices/
    # WhatsApp history for a business it has no relationship with. Same
    # ownership rule as PATCH /{patient_id} below: internal, or the
    # matching customer -- partner is never authorized here.
    if not (
        current_user["appShell"] == "internal"
        or (current_user["appShell"] == "customer" and p["org_id"] == current_user["orgId"])
    ):
        raise HTTPException(status_code=403, detail="Not authorized.")

    # Fixed (round 19): these four lines used to be
    #   find({"org_id": ..., "patient_name": p["name"]})
    # -- a patient's ENTIRE clinical timeline assembled by matching on a
    # name string. Two patients called "Ramesh Kumar" at the same clinic
    # therefore saw each other's appointments, invoices, follow-ups and
    # WhatsApp history, with nothing on screen to indicate it. Now the
    # join is on the stable patient_id written by every create path, with
    # a name fallback that applies only to rows predating the link -- see
    # linked_history_filter()'s docstring in app/utils/patients.py.
    #
    # Also parallelised: four independent reads that were awaited one
    # after another on the single most-opened screen in the Manage pillar.
    hist = linked_history_filter(p)
    appts, fups, invs, wa = await asyncio.gather(
        appointments.find(hist).sort("appointment_date", -1).limit(20).to_list(None),
        patient_followups.find(hist).sort("due_date", -1).limit(20).to_list(None),
        invoices.find(hist).sort("created_at", -1).limit(20).to_list(None),
        whatsapp_messages.find(hist).sort("created_at", -1).limit(20).to_list(None),
    )

    return {
        "patient": to_out(p), "appointments": to_out_many(appts), "followups": to_out_many(fups),
        "invoices": to_out_many(invs), "whatsapp": to_out_many(wa),
    }


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_patient(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can add patients.")
    name = body.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="name is required.")

    # phone_key/name_key are the lookup keys every write path resolves
    # against (app/utils/patients.py). Stamped at creation so a patient
    # added by hand from the Patients screen is immediately linkable by
    # the booking/billing/follow-up flows -- without them this record
    # would only be found by the slower legacy fallback.
    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "name": name,
        "phone_key": phone_key(body.get("phone")), "name_key": name_key(name),
        "phone": body.get("phone"), "email": body.get("email"), "age": body.get("age"),
        "gender": body.get("gender"), "tags": body.get("tags"), "notes": body.get("notes"),
        "last_visit_at": None, "total_visits": 0, "lifetime_value": 0,
        "created_at": now(), "updated_at": now(),
    }
    await patients.insert_one(doc)
    return {"patient": to_out(doc)}


ALLOWED_PATCH = {
    "name": "name", "phone": "phone", "email": "email", "age": "age", "gender": "gender",
    "tags": "tags", "notes": "notes", "lastVisitAt": "last_visit_at",
    "totalVisits": "total_visits", "lifetimeValue": "lifetime_value",
}


@router.patch("/{patient_id}")
async def patch_patient(patient_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    """Fixed IDOR: this previously took no current_user and never checked
    ownership, so any authenticated user (any org, even a partner account)
    could rewrite ANY business's patient record just by guessing/knowing a
    patient_id -- same bug class as billing.py/followups.py/queue.py/
    appointments.py's PATCH endpoints, all fixed together. Same ownership
    rule as GET /{patient_id} above: the owning business (any of its
    users, not owner-only -- mirrors that endpoint) or ROSKYRO internal."""
    existing = await patients.find_one({"_id": patient_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Patient not found.")
    if not (
        current_user["appShell"] == "internal"
        or (current_user["appShell"] == "customer" and existing["org_id"] == current_user["orgId"])
    ):
        raise HTTPException(status_code=403, detail="Not authorized.")

    updates = {}
    for camel, snake in ALLOWED_PATCH.items():
        if camel in body:
            updates[snake] = body[camel]
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update.")
    # Keep the lookup keys in step with the fields they derive from --
    # correcting a misspelled name or adding the phone number that was
    # missing at check-in must re-point future lookups at this record,
    # otherwise the patient silently starts accumulating a SECOND record
    # from the next appointment onward.
    if "name" in updates:
        updates["name_key"] = name_key(updates["name"])
    if "phone" in updates:
        updates["phone_key"] = phone_key(updates["phone"])
    updates["updated_at"] = now()

    await patients.update_one({"_id": patient_id}, {"$set": updates})
    updated = await patients.find_one({"_id": patient_id})
    return {"patient": to_out(updated)}


# The collections that carry a patient's history, in the order the
# backfill walks them. Label -> collection; the labels are what comes back
# in the response so the person running it can see where the work went.
_LINKABLE = (
    ("appointments", appointments),
    ("followups", patient_followups),
    ("invoices", invoices),
    ("whatsapp", whatsapp_messages),
    ("queue", queue_entries),
)


@router.post("/link-history")
async def link_history(body: dict | None = None, current_user: dict = Depends(get_current_user)):
    """One-time (re-runnable) repair for data written BEFORE patient_id
    existed.

    Every history row created from round 19 onward already carries a
    patient_id, so this endpoint only ever touches the backlog. For each
    unlinked row it re-resolves the patient from the (name, phone) the row
    already stores -- exactly the same rule the live write paths use -- and
    stamps the resulting patient_id on. Rows it links stop depending on
    the same-name fallback in linked_history_filter(), which is the whole
    point: after a successful run, two identically-named patients whose
    phone numbers differ no longer share ANY history, past or future.

    Rows it cannot resolve (no phone AND a name shared by two patients)
    are marked `patient_link_checked` so repeated runs don't re-examine
    them forever. They keep behaving exactly as they did before -- the
    name fallback still finds them -- so nothing is lost by leaving them.

    Body (all optional):
      orgId        internal callers only; customers always get their own
      dryRun       report what WOULD be linked, write nothing. Samples one
                   batch per collection rather than the whole backlog,
                   since with no writes there is no way to advance.
      createMissing  create a patient record when the history mentions
                   someone who has none. Default False -- on by choice
                   only, because it makes the Patients list grow to cover
                   everyone who has ever booked.
      limit        max rows to examine this call (default 5000, cap
                   20000). `remaining: true` in the response means there
                   is more backlog -- just call it again.
    """
    body = body or {}
    if current_user["appShell"] == "customer":
        org_id = current_user["orgId"]
    elif current_user["appShell"] == "internal" and body.get("orgId"):
        org_id = body["orgId"]
    else:
        raise HTTPException(status_code=400, detail="orgId is required.")

    dry_run = bool(body.get("dryRun"))
    create_missing = bool(body.get("createMissing"))
    raw_limit = body.get("limit")
    if raw_limit is None:
        budget = 5000
    else:
        try:
            budget = int(raw_limit)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="limit must be a whole number.")
        budget = max(1, min(budget, 20000))

    def _pending(_org_id: str) -> dict:
        return {"org_id": _org_id, "patient_id": None, "patient_link_checked": {"$ne": True}}

    report: dict = {}
    remaining = False
    for label, coll in _LINKABLE:
        stats = {"scanned": 0, "linked": 0, "unresolved": 0}
        while budget > 0:
            rows = await coll.find(_pending(org_id)).limit(min(200, budget)).to_list(None)
            if not rows:
                break
            for row in rows:
                budget -= 1
                stats["scanned"] += 1
                patient_id = await resolve_patient_id(
                    org_id, row.get("patient_name"), row.get("patient_phone"),
                    create=create_missing,
                )
                if patient_id:
                    stats["linked"] += 1
                    if not dry_run:
                        await coll.update_one({"_id": row["_id"]}, {"$set": {"patient_id": patient_id}})
                else:
                    stats["unresolved"] += 1
                    if not dry_run:
                        await coll.update_one(
                            {"_id": row["_id"]}, {"$set": {"patient_link_checked": True}}
                        )
            if dry_run:
                # Nothing was written, so the very same batch would come
                # back on the next pass -- one sample batch is the most a
                # dry run can honestly report.
                break
        if await coll.find_one(_pending(org_id)):
            remaining = True
        report[label] = stats

    return {"orgId": org_id, "dryRun": dry_run, "createMissing": create_missing,
            "remaining": remaining, "result": report}

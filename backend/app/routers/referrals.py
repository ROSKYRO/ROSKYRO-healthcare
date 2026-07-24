from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from app.db import (
    referrals, referral_status_history, referral_documents, referral_followups,
    partners, organizations, partner_categories, users, settlement_rules,
    settlements, whatsapp_messages,
)
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.audit import log_audit
from app.utils.notify import notify
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/referrals",
    tags=["referrals"],
    dependencies=[Depends(get_current_user), Depends(require_plan("connect"))],
)

# Only these business types have the right to choose/create a referral to a
# partner. Everyone else (diagnostic_lab, dental, skin_clinic, physiotherapy)
# can still list themselves as a Networking Marketing partner to be chosen by others, but
# cannot initiate a referral of their own -- see create_referral below.
REFERRAL_CREATOR_BUSINESS_TYPES = {"clinic", "hospital", "eye_hospital"}

# Referral status machine — mirrors the HREN workflow: Patient Needs Service
# -> Doctor Creates Referral -> System Generates Referral -> (ROSKYRO Review,
# if required) -> Referral Sent -> Partner Accepts/Declines -> Patient Visits
# -> Service Completed -> Report Uploaded -> Doctor Receives Report ->
# Follow-up Created -> Analytics Updated.
TRANSITIONS = {
    "draft": ["pending_review", "sent", "cancelled"],
    "pending_review": ["sent", "cancelled"],
    "sent": ["accepted", "declined", "cancelled"],
    "accepted": ["in_progress", "cancelled"],
    "declined": [],
    "in_progress": ["report_uploaded", "cancelled"],
    "report_uploaded": ["completed"],
    "completed": [],
    "cancelled": [],
}


async def next_referral_code() -> str:
    n = await referrals.count_documents({})
    return f"RSK-REF-{str(n + 1).zfill(6)}"


async def add_history(referral_id: str, status: str, changed_by: str | None, note: str | None):
    await referral_status_history.insert_one({
        "_id": new_id(),
        "referral_id": referral_id,
        "status": status,
        "note": note,
        "changed_by": changed_by,
        "changed_at": now(),
    })


async def _notify_patient_whatsapp(referral: dict, event: str) -> dict | None:
    """The patient has no ROSKYRO account and never logs into the app, so
    the only way they find out *where* and *to whom* they've been
    referred is a WhatsApp message sent straight to `patient_phone` at
    each lifecycle event that actually matters to them. This is a
    simulated send -- same as routers/whatsapp.py, no real WhatsApp
    Business API in v1 -- but it's logged as a genuine outbound
    `whatsapp_messages` row against the *referring* business's org (not
    just a side-effect nobody can see), so it shows up in that business's
    own WhatsApp Communication log (`/app/whatsapp`) too, and is surfaced
    back on the referral detail view for both the referring business and
    the partner to see exactly what the patient was told, and when.
    Silently skips (returns None) if there's no patient_phone on file --
    never blocks the referral flow itself.

    Every patient-facing message is branded as ROSKYRO doing the
    referring, never the specific business -- the referring business's
    name/identity is intentionally never mentioned to the patient here
    (it stays visible only inside the app, to the business's own staff
    and to ROSKYRO internal, via referring_doctor_name/referring_org_name
    on the referral detail views)."""
    if not referral.get("patient_phone"):
        return None
    partner = await partners.find_one({"_id": referral["partner_id"]})
    if not partner:
        return None
    partner_org = await organizations.find_one({"_id": partner["org_id"]})
    partner_name = partner_org.get("name") if partner_org else "the partner"
    partner_phone = partner.get("contact_phone") or (partner_org.get("phone") if partner_org else None)
    partner_city = partner_org.get("city") if partner_org else None
    location_bit = f", {partner_city}" if partner_city else ""
    contact_bit = f" Contact: {partner_phone}." if partner_phone else ""

    messages = {
        "sent": (
            f"Hi {referral['patient_name']}, ROSKYRO Health Network ki taraf se aapko {partner_name}{location_bit} "
            f"ke paas refer kiya gaya hai ({referral['service_requested']} ke liye).{contact_bit} "
            f"Aapka referral code: {referral['referral_code']}. Koi sawaal ho to ROSKYRO se sampark karein."
        ),
        "accepted": (
            f"Hi {referral['patient_name']}, {partner_name} ne ROSKYRO Health Network se mila aapka referral "
            f"accept kar liya hai.{contact_bit or ' Details ke liye ROSKYRO se sampark karein.'}"
        ),
        "report_uploaded": (
            f"Hi {referral['patient_name']}, {partner_name} ne aapki report taiyar kar di hai. "
            f"Kripya report review ke liye ROSKYRO se sampark karein."
        ),
        "completed": (
            f"Hi {referral['patient_name']}, ROSKYRO Health Network dwara kiya gaya aapka referral "
            f"({referral['referral_code']}) {partner_name} ke saath complete ho gaya hai. Dhanyawaad!"
        ),
    }
    message = messages.get(event)
    if not message:
        return None

    doc = {
        "_id": new_id(), "org_id": referral["referring_org_id"], "referral_id": referral["_id"],
        "patient_name": referral["patient_name"], "patient_phone": referral["patient_phone"],
        "direction": "outbound", "template_name": f"referral_{event}", "message": message,
        "status": "sent", "sent_by": None, "created_at": now(),
    }
    await whatsapp_messages.insert_one(doc)
    return doc


async def _enrich_list(rows: list[dict]) -> list[dict]:
    """Manual joins standing in for referrals.js's SQL JOIN across
    organizations/partners/partner_categories/users -- fetch related docs
    by id and merge in application code (kept deliberately explicit rather
    than a Mongo $lookup aggregation, for mongomock compatibility + clarity)."""
    out = []
    for r in rows:
        ro = await organizations.find_one({"_id": r["referring_org_id"]})
        p = await partners.find_one({"_id": r["partner_id"]})
        po = await organizations.find_one({"_id": p["org_id"]}) if p else None
        pc = await partner_categories.find_one({"_id": r["category_id"]})
        du = await users.find_one({"_id": r["referring_user_id"]})
        item = to_out(r)
        item["referring_org_name"] = ro.get("name") if ro else None
        item["partner_org_name"] = po.get("name") if po else None
        item["category_name"] = pc.get("name") if pc else None
        item["category_slug"] = pc.get("slug") if pc else None
        item["referring_doctor_name"] = du.get("name") if du else None
        out.append(item)
    return out


@router.get("")
@router.get("/")
async def list_referrals(
    status: str | None = None,
    category: str | None = None,
    q: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    filt: dict = {}
    if current_user["appShell"] == "customer":
        filt["referring_org_id"] = current_user["orgId"]
    elif current_user["appShell"] == "partner":
        org_partners = await partners.find({"org_id": current_user["orgId"]}).to_list(None)
        partner_ids = [p["_id"] for p in org_partners]
        filt["partner_id"] = {"$in": partner_ids}
    # internal: no default scoping (sees everything), but can filter below.

    if status:
        filt["status"] = status
    if q:
        filt["$or"] = [
            {"patient_name": {"$regex": q, "$options": "i"}},
            {"referral_code": {"$regex": q, "$options": "i"}},
        ]

    rows = await referrals.find(filt).sort("created_at", -1).limit(300).to_list(None)

    if category:
        cat = await partner_categories.find_one({"slug": category})
        cat_id = cat["_id"] if cat else "__none__"
        rows = [r for r in rows if r.get("category_id") == cat_id]

    return {"referrals": await _enrich_list(rows)}


@router.get("/{referral_id}")
async def get_referral(referral_id: str, current_user: dict = Depends(get_current_user)):
    referral = await referrals.find_one({"_id": referral_id})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found.")

    partner = await partners.find_one({"_id": referral["partner_id"]})
    partner_org_id = partner["org_id"] if partner else None

    if current_user["appShell"] == "customer" and referral["referring_org_id"] != current_user["orgId"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this referral.")
    if current_user["appShell"] == "partner" and partner_org_id != current_user["orgId"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this referral.")

    ro = await organizations.find_one({"_id": referral["referring_org_id"]})
    po = await organizations.find_one({"_id": partner_org_id}) if partner_org_id else None
    pc = await partner_categories.find_one({"_id": referral["category_id"]})
    du = await users.find_one({"_id": referral["referring_user_id"]})

    out = to_out(referral)
    out["referring_org_name"] = ro.get("name") if ro else None
    out["partner_org_name"] = po.get("name") if po else None
    out["partner_org_id"] = partner_org_id
    out["category_name"] = pc.get("name") if pc else None
    out["referring_doctor_name"] = du.get("name") if du else None
    out["referring_doctor_email"] = du.get("email") if du else None

    history = await referral_status_history.find({"referral_id": referral_id}).sort("changed_at", 1).to_list(None)
    documents = await referral_documents.find({"referral_id": referral_id}).sort("uploaded_at", -1).to_list(None)
    followups = await referral_followups.find({"referral_id": referral_id}).sort("created_at", -1).to_list(None)
    # What the patient was actually told, and when -- surfaced to both the
    # referring business and the partner so it's clear the patient already
    # knows where they've been referred, without either side having to ask.
    patient_notifications = await whatsapp_messages.find({"referral_id": referral_id}).sort("created_at", 1).to_list(None)

    return {
        "referral": out,
        "history": to_out_many(history),
        "documents": to_out_many(documents),
        "followups": to_out_many(followups),
        "patient_notifications": to_out_many(patient_notifications),
    }


class CreateReferralBody(BaseModel):
    partnerId: str
    patientName: str
    patientPhone: str | None = None
    patientAge: int | None = None
    patientGender: str | None = None
    serviceRequested: str
    clinicalNotes: str | None = None
    urgency: str | None = None
    aiPartnerSuggested: bool = False


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_referral(body: CreateReferralBody, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can create a referral.")

    # Access control: only certain business types have the right to choose/
    # create a referral to a partner. Everyone else can still list
    # themselves as a partner (see routers/partners.py's register_partner,
    # which is deliberately left unrestricted) -- they just can't initiate
    # one of their own.
    if current_user.get("businessType") not in REFERRAL_CREATOR_BUSINESS_TYPES:
        raise HTTPException(
            status_code=403,
            detail="Your business type isn't eligible to create referrals. You can still list yourself as a "
                   "Networking Marketing partner so other businesses can refer patients to you.",
        )

    partner = await partners.find_one({"_id": body.partnerId})
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found.")

    # Emergency-urgency referrals to an unverified partner get flagged for a
    # human review gate before sending, per the AI+Human safety model.
    requires_review = partner.get("verification_status") != "verified"
    code = await next_referral_code()
    initial_status = "pending_review" if requires_review else "sent"
    referral_id = new_id()
    ts = now()

    referral_doc = {
        "_id": referral_id,
        "referral_code": code,
        "referring_org_id": current_user["orgId"],
        "referring_user_id": current_user["id"],
        "partner_id": body.partnerId,
        "category_id": partner.get("category_id"),
        "patient_name": body.patientName,
        "patient_phone": body.patientPhone,
        "patient_age": body.patientAge,
        "patient_gender": body.patientGender,
        "service_requested": body.serviceRequested,
        "clinical_notes": body.clinicalNotes,
        "urgency": body.urgency or "routine",
        "status": initial_status,
        "ai_partner_suggested": bool(body.aiPartnerSuggested),
        "requires_roskyro_review": requires_review,
        "sent_at": ts if initial_status == "sent" else None,
        "accepted_at": None,
        "declined_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "decline_reason": None,
        "created_at": ts,
        "updated_at": ts,
    }
    await referrals.insert_one(referral_doc)

    await add_history(referral_id, "draft", current_user["id"], "Referral created by referring doctor.")
    if initial_status == "sent":
        await add_history(referral_id, "sent", current_user["id"], "Auto-sent: partner is pre-verified.")
    else:
        await add_history(referral_id, "pending_review", current_user["id"], "Held for ROSKYRO review: partner not yet verified.")
        from app.db import tasks as tasks_col
        await tasks_col.insert_one({
            "_id": new_id(),
            "org_id": current_user["orgId"],
            "related_type": "referral",
            "related_id": referral_id,
            "title": f"Review referral {code} before sending",
            "description": "Referral to an unverified partner. Confirm details before it reaches the partner.",
            "task_type": "referral_review",
            "assigned_role": "roskyro_ops_manager",
            "assigned_to": None,
            "priority": "high",
            "status": "open",
            "sla_hours": 4,
            "sla_due_at": now(),
            "created_by": current_user["id"],
            "completed_at": None,
            "created_at": now(),
        })

    await referral_documents.insert_one({
        "_id": new_id(), "referral_id": referral_id, "doc_type": "referral_slip",
        "file_name": f"{code}-referral-slip.pdf", "file_url": f"/generated/referral-slips/{code}.pdf",
        "uploaded_by": current_user["id"], "uploaded_at": now(),
    })
    await referral_documents.insert_one({
        "_id": new_id(), "referral_id": referral_id, "doc_type": "qr_code",
        "file_name": f"{code}-qr.png", "file_url": f"/generated/qr/{code}.png",
        "uploaded_by": current_user["id"], "uploaded_at": now(),
    })

    if initial_status == "sent":
        partner_owner = await users.find_one({"org_id": partner["org_id"], "role": "partner_admin"})
        if partner_owner:
            await notify(
                partner_owner["_id"], "referral_received", f"New referral {code}",
                f"{body.patientName} referred for {body.serviceRequested}.",
                "referral", referral_id,
            )
        # Patient has no ROSKYRO login -- this is how they actually find
        # out where/to whom they've been referred (see helper docstring).
        await _notify_patient_whatsapp(referral_doc, "sent")

    await log_audit(current_user["id"], "referral.created", "referral", referral_id, {"code": code, "initialStatus": initial_status})
    return {"referral": to_out(referral_doc)}


class TransitionBody(BaseModel):
    status: str
    note: str | None = None
    declineReason: str | None = None


@router.post("/{referral_id}/transition")
async def transition_referral(referral_id: str, body: TransitionBody, current_user: dict = Depends(get_current_user)):
    referral = await referrals.find_one({"_id": referral_id})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found.")
    partner = await partners.find_one({"_id": referral["partner_id"]})
    partner_org_id = partner["org_id"] if partner else None

    allowed = TRANSITIONS.get(referral["status"], [])
    if body.status not in allowed:
        raise HTTPException(status_code=400, detail={
            "error": f"Cannot move referral from '{referral['status']}' to '{body.status}'.",
            "allowedNext": allowed,
        })

    referring_side = current_user["appShell"] == "customer" and current_user["orgId"] == referral["referring_org_id"]
    partner_side = current_user["appShell"] == "partner" and current_user["orgId"] == partner_org_id
    internal = current_user["appShell"] == "internal"

    partner_only_actions = ["accepted", "declined", "in_progress", "report_uploaded"]

    if body.status in partner_only_actions and not (partner_side or internal):
        raise HTTPException(status_code=403, detail="Only the receiving partner can perform this action.")
    if referral["status"] in ["sent", "pending_review"] and body.status == "cancelled" and not (referring_side or internal):
        raise HTTPException(status_code=403, detail="Only the referring business can cancel a referral at this stage.")
    if body.status == "completed" and not (referring_side or internal):
        raise HTTPException(status_code=403, detail="Only the referring business marks a referral as fully completed (after reviewing the report).")
    if body.status == "sent" and referral["status"] == "pending_review" and not internal:
        raise HTTPException(status_code=403, detail="Only ROSKYRO ops can release a referral that is pending review.")

    timestamp_field = {
        "sent": "sent_at", "accepted": "accepted_at", "declined": "declined_at",
        "completed": "completed_at", "cancelled": "cancelled_at",
    }.get(body.status)

    updates = {"status": body.status, "updated_at": now()}
    if timestamp_field:
        updates[timestamp_field] = now()
    if body.status == "declined" and body.declineReason:
        updates["decline_reason"] = body.declineReason

    await referrals.update_one({"_id": referral_id}, {"$set": updates})
    await add_history(referral_id, body.status, current_user["id"], body.note)

    # Auto-create a follow-up task when a report is uploaded, per the
    # documented workflow: Report Uploaded -> Doctor Receives Report ->
    # Follow-up Created.
    if body.status == "report_uploaded":
        from datetime import timedelta
        await referral_followups.insert_one({
            "_id": new_id(), "referral_id": referral_id,
            "due_date": (now() + timedelta(days=3)).date().isoformat(),
            "note": "Review report with patient and confirm next steps.",
            "status": "pending", "created_by": current_user["id"], "created_at": now(),
        })
        await partners.update_one({"_id": referral["partner_id"]}, {
            "$inc": {"total_referrals_completed": 1}, "$set": {"updated_at": now()},
        })
    if body.status == "accepted":
        await partners.update_one({"_id": referral["partner_id"]}, {
            "$inc": {"total_referrals_received": 1}, "$set": {"updated_at": now()},
        })
    if body.status == "completed":
        # Generate settlement if a rule applies (resolution order:
        # org_partner_pair > partner > org > platform default 'none').
        rule = None
        for scope_filt in (
            {"scope": "org_partner_pair", "org_id": referral["referring_org_id"], "partner_id": referral["partner_id"]},
            {"scope": "partner", "partner_id": referral["partner_id"]},
            {"scope": "org", "org_id": referral["referring_org_id"]},
            {"scope": "platform"},
        ):
            rule = await settlement_rules.find_one({**scope_filt, "is_active": True})
            if rule:
                break
        if rule and rule.get("settlement_type") != "none":
            # Marketing Fee: a flat rupee amount only -- no percentage-of-
            # service-price calculation (see settlements.py, where
            # "percentage" was removed as a valid settlement_type). Owed by
            # the PARTNER to ROSKYRO (the referral is treated as marketing
            # the referring business did for the partner) -- org_id is kept
            # here purely for period-based attribution (which referring
            # business generated this fee), not as who owes the money.
            amount = float(rule.get("flat_fee_amount") or 0) if rule["settlement_type"] == "flat_fee" else 0
            await settlements.insert_one({
                "_id": new_id(), "referral_id": referral_id, "rule_id": rule["_id"],
                "org_id": referral["referring_org_id"], "partner_id": referral["partner_id"],
                "settlement_type": rule["settlement_type"], "amount": amount,
                "period_month": now().strftime("%Y-%m"), "status": "pending",
                "paid_at": None, "payer_marked_paid_at": None, "confirmed_by": None,
                "included_in_payout_id": None, "created_at": now(),
            })

    # Notifications
    notify_map = {
        "sent": {"toPartner": True, "title": "New referral received", "type": "referral_received"},
        "accepted": {"toReferrer": True, "title": "Partner accepted the referral", "type": "referral_accepted"},
        "declined": {"toReferrer": True, "title": "Partner declined the referral", "type": "referral_declined"},
        "report_uploaded": {"toReferrer": True, "title": "Report uploaded — ready to review", "type": "report_uploaded"},
        "completed": {"toPartner": True, "title": "Referral marked completed", "type": "referral_completed"},
    }
    n = notify_map.get(body.status)
    if n:
        if n.get("toPartner"):
            partner_user = await users.find_one({"org_id": partner_org_id, "role": "partner_admin"})
            if partner_user:
                await notify(partner_user["_id"], n["type"], n["title"], f"Referral {referral['referral_code']}", "referral", referral_id)
        if n.get("toReferrer"):
            await notify(referral["referring_user_id"], n["type"], n["title"], f"Referral {referral['referral_code']}", "referral", referral_id)

    await log_audit(current_user["id"], "referral.status_changed", "referral", referral_id, {"from": referral["status"], "to": body.status})
    updated = await referrals.find_one({"_id": referral_id})

    # Patient-facing WhatsApp update for the lifecycle events they
    # actually need to know about. "sent" here covers a referral that
    # was held for ROSKYRO review and is only now being released to the
    # partner -- create_referral already notified the patient directly
    # when no review was needed, so this doesn't double-send for that path.
    if body.status in ("sent", "accepted", "report_uploaded", "completed"):
        await _notify_patient_whatsapp(updated, body.status)

    return {"referral": to_out(updated)}


class DocumentBody(BaseModel):
    docType: str
    fileName: str


@router.post("/{referral_id}/documents", status_code=201)
async def add_document(referral_id: str, body: DocumentBody, current_user: dict = Depends(get_current_user)):
    referral = await referrals.find_one({"_id": referral_id})
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found.")

    import time
    file_url = f"/generated/uploads/{referral_id}/{int(time.time() * 1000)}-{body.fileName}"
    doc = {
        "_id": new_id(), "referral_id": referral_id, "doc_type": body.docType,
        "file_name": body.fileName, "file_url": file_url,
        "uploaded_by": current_user["id"], "uploaded_at": now(),
    }
    await referral_documents.insert_one(doc)
    await log_audit(current_user["id"], "referral.document_uploaded", "referral", referral_id, {"docType": body.docType, "fileName": body.fileName})
    return {"document": to_out(doc)}


@router.get("/{referral_id}/timeline")
async def timeline(referral_id: str):
    history = await referral_status_history.find({"referral_id": referral_id}).sort("changed_at", 1).to_list(None)
    return {"timeline": to_out_many(history)}

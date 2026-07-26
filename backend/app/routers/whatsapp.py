from fastapi import APIRouter, HTTPException, Depends

from app.db import whatsapp_messages, organizations
from app.auth import get_current_user, require_internal
from app.utils.plans import require_plan
from app.utils.ids import now, to_out, to_out_many
from app.utils.whatsapp_sender import dispatch_message

router = APIRouter(
    prefix="/api/whatsapp", tags=["whatsapp"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)
# Note: require_plan() above never blocks internal/partner users (only
# customer-shell users are pillar-gated -- see app/utils/plans.py), so the
# /queue endpoints below can live on this same router: they only add
# require_internal, which is what actually restricts them to ROSKYRO ops.

TEMPLATES = {
    "appointment_reminder": lambda name: f"Hi {name}, this is a reminder for your upcoming appointment. Reply CONFIRM to confirm or CALL if you need to reschedule.",
    "followup_nudge": lambda name: f"Hi {name}, it's time for your follow-up visit. Please call us or reply to book a convenient slot.",
    "review_request": lambda name: f"Thank you for visiting us, {name}! We'd really appreciate a quick Google review — it helps other patients find quality care.",
    "invoice_link": lambda name: f"Hi {name}, your invoice is ready. Please find the payment details attached.",
}


@router.get("")
@router.get("/")
async def list_messages(orgId: str | None = None, current_user: dict = Depends(get_current_user)):
    org_id = current_user["orgId"] if current_user["appShell"] == "customer" else orgId
    if not org_id:
        raise HTTPException(status_code=400, detail="orgId is required.")
    rows = await whatsapp_messages.find({"org_id": org_id}).sort("created_at", -1).limit(200).to_list(None)
    return {"messages": to_out_many(rows)}


@router.post("/send", status_code=201)
async def send_message(body: dict, current_user: dict = Depends(get_current_user)):
    """Routed through the shared dispatch choke point (app/utils/
    whatsapp_sender.py) instead of inserting straight into
    whatsapp_messages -- today that means this lands in the centralized
    ROSKYRO-ops queue (see /queue below) with a ready-to-open wa.me link,
    same as every automatic referral-lifecycle message; if a real
    WhatsApp API is ever wired up (WHATSAPP_MODE=api), this call site
    doesn't change at all."""
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can send messages.")
    patient_name, patient_phone = body.get("patientName"), body.get("patientPhone")
    if not patient_name or not patient_phone:
        raise HTTPException(status_code=400, detail="patientName and patientPhone are required.")

    template_name = body.get("templateName")
    final_message = body.get("message") or (TEMPLATES[template_name](patient_name) if template_name in TEMPLATES else None)
    if not final_message:
        raise HTTPException(status_code=400, detail="Provide either a message or a known templateName.")

    doc = await dispatch_message(
        org_id=current_user["orgId"], patient_name=patient_name, patient_phone=patient_phone,
        message=final_message, template_name=template_name, sent_by=current_user["id"],
    )
    return {"message": to_out(doc), "templates": list(TEMPLATES.keys())}


@router.get("/templates")
async def list_templates():
    return {"templates": [{"key": k, "preview": fn("Patient Name")} for k, fn in TEMPLATES.items()]}


@router.get("/queue")
async def list_queue(current_user: dict = Depends(get_current_user), _internal: dict = Depends(require_internal)):
    """ROSKYRO-ops-only, platform-wide (deliberately NOT scoped to any one
    business's org_id, unlike GET /api/whatsapp above) -- this is the
    single shared queue every business's pending patient messages funnel
    into, regardless of which business/computer created them, so that ONE
    centralized WhatsApp Web/Business session (see module docstring in
    app/utils/whatsapp_sender.py) can dispatch all of them. Sorted oldest
    first (FIFO) so nothing sits forgotten at the bottom, and capped at
    300 like every other platform-wide admin list in this codebase."""
    rows = await whatsapp_messages.find({"status": "queued"}).sort("created_at", 1).limit(300).to_list(None)

    # Batch-fetch the referring org ONCE via $in, instead of a find_one
    # per row -- same fixed-query-count pattern used everywhere else in
    # this codebase's list endpoints.
    org_ids = list({m["org_id"] for m in rows if m.get("org_id")})
    org_docs = await organizations.find({"_id": {"$in": org_ids}}).to_list(None) if org_ids else []
    orgs_by_id = {o["_id"]: o for o in org_docs}

    out = []
    for m in rows:
        org = orgs_by_id.get(m.get("org_id"))
        item = to_out(m)
        item["org_name"] = org.get("name") if org else None
        out.append(item)
    return {"queue": out}


@router.post("/queue/{message_id}/dispatch")
async def dispatch_queued_message(message_id: str, current_user: dict = Depends(get_current_user), _internal: dict = Depends(require_internal)):
    """Marks a queued message as actually sent -- called once the ops
    user has opened the message's wa_link (which pre-fills the chat) and
    hit Enter in their own WhatsApp Web/Business session. This is the
    one-click "I sent this" confirmation; it does not itself contact
    WhatsApp in any way (there's no API integration to call in "queue"
    mode -- see app/utils/whatsapp_sender.py), it just finalizes the
    record so the same message doesn't linger in the shared queue."""
    msg = await whatsapp_messages.find_one({"_id": message_id})
    if not msg:
        raise HTTPException(status_code=404, detail="Queued message not found.")
    if msg["status"] != "queued":
        raise HTTPException(status_code=400, detail="This message has already been dispatched.")

    await whatsapp_messages.update_one(
        {"_id": message_id},
        {"$set": {"status": "sent", "dispatched_by": current_user["id"], "dispatched_at": now()}},
    )
    updated = await whatsapp_messages.find_one({"_id": message_id})
    return {"message": to_out(updated)}

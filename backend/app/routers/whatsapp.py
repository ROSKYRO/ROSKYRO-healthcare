from fastapi import APIRouter, HTTPException, Depends

from app.db import whatsapp_messages
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many

router = APIRouter(
    prefix="/api/whatsapp", tags=["whatsapp"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)

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
    """Simulated send (no external WhatsApp Business API in v1; the response
    shape matches what a real integration returns)."""
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can send messages.")
    patient_name, patient_phone = body.get("patientName"), body.get("patientPhone")
    if not patient_name or not patient_phone:
        raise HTTPException(status_code=400, detail="patientName and patientPhone are required.")

    template_name = body.get("templateName")
    final_message = body.get("message") or (TEMPLATES[template_name](patient_name) if template_name in TEMPLATES else None)
    if not final_message:
        raise HTTPException(status_code=400, detail="Provide either a message or a known templateName.")

    doc = {
        "_id": new_id(), "org_id": current_user["orgId"], "patient_name": patient_name,
        "patient_phone": patient_phone, "direction": "outbound", "template_name": template_name,
        "message": final_message, "status": "sent", "sent_by": current_user["id"], "created_at": now(),
    }
    await whatsapp_messages.insert_one(doc)
    return {"message": to_out(doc), "templates": list(TEMPLATES.keys())}


@router.get("/templates")
async def list_templates():
    return {"templates": [{"key": k, "preview": fn("Patient Name")} for k, fn in TEMPLATES.items()]}

"""Single choke point for actually getting a patient-facing WhatsApp
message "sent" -- every caller (referrals.py's automatic lifecycle
messages, whatsapp.py's manual send form) goes through `dispatch_message()`
and never has to know or care HOW the message actually leaves the
building. That's what makes switching delivery modes later a one-line
config change instead of a rewrite.

Today (WHATSAPP_MODE="queue", the default -- see app/config.py): there's
no paid WhatsApp Business/Cloud API wired up, so a message can't actually
be pushed out from Python code alone. Instead, every message is inserted
into `whatsapp_messages` with status="queued" plus a ready-to-open wa.me
click-to-chat deep link (`wa_link`) -- WhatsApp's own free, no-API-key,
no-Meta-approval link format. ONE ROSKYRO ops device stays logged into
ROSKYRO's WhatsApp Web/Business App with the official number (optionally
mirrored to a couple more ops machines via WhatsApp's own "Linked
Devices" feature, up to ~4 total) -- that team works a single shared
queue (GET /api/whatsapp/queue, platform-wide, not scoped to any one
business) and dispatches each pending message with one click: open
wa_link (pre-fills the text, just hit Enter), then POST .../dispatch to
mark it sent. This is what actually solves "one WhatsApp login can't run
on every business's own computer" -- no matter which business, on which
computer, triggered the message, sending always happens from that one
centralized session, so it's free and doesn't violate WhatsApp's terms
(unlike self-hosted WhatsApp-Web-automation libraries, which do).

Tomorrow (WHATSAPP_MODE="api"): flip the env var once a real WhatsApp
Business/Cloud API (or any BSP) is integrated, fill in WHATSAPP_API_TOKEN
/ WHATSAPP_API_PHONE_NUMBER_ID (app/config.py), and implement
`_send_via_official_api` below. referrals.py and whatsapp.py never
change, because they only ever call `dispatch_message()` -- this module
is the only thing that knows which mode is active.
"""
from urllib.parse import quote

from app.db import whatsapp_messages
from app.config import WHATSAPP_MODE
from app.utils.ids import new_id, now
from app.utils.phone import normalize_phone


def build_wa_link(phone: str | None, message: str) -> str | None:
    """WhatsApp's own free "click-to-chat" deep link (`wa.me/<number>?text=`)
    -- no API key, no Meta Business approval, opens a pre-filled chat in
    whatever WhatsApp Web/App session is active on the device that opens
    it. Needs a phone number in international format (country code +
    digits only); returns None if we don't have enough digits to build
    one, since a malformed wa.me link just silently fails to open a chat
    rather than raising anything actionable.

    `normalize_phone` (app/utils/phone.py) always returns a bare 10-digit
    Indian mobile number (or fewer digits if that's all that was on
    file) -- never a country code, since that's how phone numbers are
    stored/matched everywhere else in this codebase. Every seeded/real
    number in this build is Indian, so we prefix +91 by default here; a
    number that already carries a country code (more than 10 digits) is
    passed through unchanged."""
    digits = normalize_phone(phone)
    if len(digits) < 10:
        return None
    full_number = digits if len(digits) > 10 else f"91{digits}"
    return f"https://wa.me/{full_number}?text={quote(message)}"


async def dispatch_message(
    *, org_id: str | None, patient_name: str, patient_phone: str, message: str,
    template_name: str | None = None, referral_id: str | None = None, sent_by: str | None = None,
) -> dict:
    """The one function every caller uses to get a patient-facing
    WhatsApp message out the door. Always returns the `whatsapp_messages`
    document that was inserted (status "queued" today, or whatever the
    real API integration settles on once WHATSAPP_MODE="api")."""
    if WHATSAPP_MODE == "api":
        return await _send_via_official_api(
            org_id=org_id, patient_name=patient_name, patient_phone=patient_phone, message=message,
            template_name=template_name, referral_id=referral_id, sent_by=sent_by,
        )

    # Default / WHATSAPP_MODE == "queue".
    #
    # Round 19: link the message to a patient record so patients.py's
    # history joins on the id rather than the name (two same-named
    # patients used to see each other's WhatsApp history). create=False
    # deliberately -- messages also go out for referral patients who may
    # belong to another business entirely, and a message is not a reason
    # to invent a patient record. Imported here rather than at module
    # scope because app.utils.patients imports app.db, and this module is
    # pulled in from routers that app.db's own import chain touches.
    from app.utils.patients import safe_resolve_patient_id

    patient_id = await safe_resolve_patient_id(
        org_id, patient_name, patient_phone, create=False
    ) if org_id else None

    doc = {
        "_id": new_id(), "org_id": org_id, "referral_id": referral_id,
        "patient_name": patient_name, "patient_id": patient_id,
        "patient_phone": patient_phone,
        "direction": "outbound", "template_name": template_name, "message": message,
        "wa_link": build_wa_link(patient_phone, message),
        "status": "queued", "sent_by": sent_by,
        "dispatched_by": None, "dispatched_at": None,
        "created_at": now(),
    }
    await whatsapp_messages.insert_one(doc)
    return doc


async def _send_via_official_api(
    *, org_id, patient_name, patient_phone, message, template_name, referral_id, sent_by,
) -> dict:
    """Stub for the future real integration (WhatsApp Business/Cloud API,
    or any BSP that wraps it) -- implement the actual HTTP call to the
    provider here using WHATSAPP_API_TOKEN / WHATSAPP_API_PHONE_NUMBER_ID
    (app/config.py), then flip WHATSAPP_MODE=api. Deliberately raises
    instead of silently falling back to the queue, so a deployment that
    sets WHATSAPP_MODE=api by mistake (before this is actually wired up)
    fails loudly rather than quietly dropping every patient message."""
    raise NotImplementedError(
        "WHATSAPP_MODE=api is set but _send_via_official_api() isn't implemented yet -- wire up the "
        "real WhatsApp Business/Cloud API call here (see WHATSAPP_API_TOKEN / WHATSAPP_API_PHONE_NUMBER_ID "
        "in app/config.py), or set WHATSAPP_MODE=queue to use the centralized click-to-chat queue instead."
    )

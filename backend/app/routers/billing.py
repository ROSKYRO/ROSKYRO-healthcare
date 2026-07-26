from fastapi import APIRouter, HTTPException, Depends

from app.db import invoices
from app.auth import get_current_user
from app.utils.plans import require_plan
from app.utils.ids import new_id, now, to_out, to_out_many
from app.utils.counters import next_sequence

router = APIRouter(
    prefix="/api/billing", tags=["billing"],
    dependencies=[Depends(get_current_user), Depends(require_plan("manage"))],
)


async def next_invoice_number() -> str:
    # Atomic $inc counter, not count_documents({}) -- see app/utils/counters.py.
    n = await next_sequence("billing_invoice_number", bootstrap=lambda: invoices.count_documents({}))
    return f"INV-{str(n).zfill(6)}"


def compute_totals(line_items: list, discount: float = 0, tax_rate: float = 0) -> dict:
    subtotal = sum(float(i.get("quantity") or 1) * float(i.get("unitPrice") or 0) for i in (line_items or []))
    taxed = max(0, subtotal - float(discount or 0))
    tax = round(taxed * (float(tax_rate or 0) / 100), 2)
    total = round(taxed + tax, 2)
    return {"subtotal": round(subtotal, 2), "tax": tax, "total": total}


@router.get("")
@router.get("/")
async def list_invoices(orgId: str | None = None, status: str | None = None, current_user: dict = Depends(get_current_user)):
    # Only "customer" (own org) or "internal" with an explicit orgId may
    # scope this query -- a "partner" shell previously fell into the same
    # `else orgId` branch as internal, so a partner account could pass an
    # arbitrary ?orgId= and read another business's data. Fixed: partner
    # (and any other non-customer, non-internal shell) is rejected here.
    if current_user["appShell"] == "customer":
        org_id = current_user["orgId"]
    elif current_user["appShell"] == "internal" and orgId:
        org_id = orgId
    else:
        raise HTTPException(status_code=400, detail="orgId is required.")

    filt: dict = {"org_id": org_id}
    if status:
        filt["status"] = status
    rows = await invoices.find(filt).sort("created_at", -1).limit(300).to_list(None)
    return {"invoices": to_out_many(rows)}


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def create_invoice(body: dict, current_user: dict = Depends(get_current_user)):
    if current_user["appShell"] != "customer":
        raise HTTPException(status_code=403, detail="Only a healthcare business user can create invoices.")
    patient_name = body.get("patientName")
    line_items = body.get("lineItems")
    if not patient_name or not isinstance(line_items, list) or not line_items:
        raise HTTPException(status_code=400, detail="patientName and at least one line item are required.")

    totals = compute_totals(line_items, body.get("discount"), body.get("taxRate"))
    invoice_number = await next_invoice_number()

    doc = {
        "_id": new_id(), "invoice_number": invoice_number, "org_id": current_user["orgId"],
        "patient_name": patient_name, "patient_phone": body.get("patientPhone"),
        "appointment_id": body.get("appointmentId"), "line_items": line_items,
        "subtotal": totals["subtotal"], "discount": body.get("discount") or 0, "tax": totals["tax"],
        "total": totals["total"], "due_date": body.get("dueDate"), "created_by": current_user["id"],
        "status": "draft", "paid_at": None, "created_at": now(),
    }
    await invoices.insert_one(doc)
    return {"invoice": to_out(doc)}


@router.patch("/{invoice_id}")
async def patch_invoice(invoice_id: str, body: dict, current_user: dict = Depends(get_current_user)):
    """Fixed IDOR: this previously took no current_user and never checked
    ownership, so any authenticated user (any org) could mark ANY
    business's invoice paid/cancelled just by guessing/knowing an
    invoice_id -- same bug class fixed together across patients.py/
    followups.py/queue.py/appointments.py."""
    existing = await invoices.find_one({"_id": invoice_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    if not (
        current_user["appShell"] == "internal"
        or (current_user["appShell"] == "customer" and existing["org_id"] == current_user["orgId"])
    ):
        raise HTTPException(status_code=403, detail="Not authorized.")

    status = body.get("status")
    if status not in ("draft", "sent", "paid", "overdue", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status.")

    updates = {"status": status}
    if status == "paid":
        updates["paid_at"] = now()

    await invoices.update_one({"_id": invoice_id}, {"$set": updates})
    updated = await invoices.find_one({"_id": invoice_id})
    return {"invoice": to_out(updated)}

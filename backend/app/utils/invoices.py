"""PDF invoice generation. Two invoice types share this module's reportlab
boilerplate: the Marketing Fee Payout invoice (ROSKYRO -> business, see
routers/settlements.py) and the subscription renewal invoice (business ->
ROSKYRO, see routers/subscription_renewals.py) -- money flows opposite
directions for these two, so keep the wording on each invoice specific to
which one it is."""
import io

from app.utils.ids import now


def render_marketing_payout_invoice_pdf(payout: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()

    generated_at = now()
    status_label = "PAID" if payout.get("status") == "paid" else "PENDING"

    elements = [
        Paragraph("<b>ROSKYRO Healthcare OS</b>", styles["Title"]),
        Paragraph("Marketing Fee Payout Invoice", styles["Heading2"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Invoice No: <b>{payout.get('invoice_number', '—')}</b>", styles["Normal"]),
        Paragraph(f"Invoice Date: {generated_at.strftime('%d %b %Y')}", styles["Normal"]),
        Paragraph(f"Status: <b>{status_label}</b>" + (f" (paid {payout['paid_at'].strftime('%d %b %Y')})" if payout.get("paid_at") else ""), styles["Normal"]),
        Spacer(1, 6 * mm),
        Paragraph(f"<b>Billed to:</b> {payout.get('org_name') or '—'}", styles["Normal"]),
        Paragraph(f"<b>Period covered:</b> {payout.get('period') or '—'}", styles["Normal"]),
        Spacer(1, 6 * mm),
    ]

    data = [
        ["Description", "Value"],
        ["Completed referrals attributed to this business this period", str(payout.get("referral_count", 0))],
        ["Total Marketing Fees ROSKYRO collected from partners on these referrals", f"₹{float(payout.get('total_fees_collected') or 0):,.2f}"],
        ["Marketing Fee Payout rate", f"{payout.get('payout_percentage', 0)}%"],
        ["Marketing Fee Payout amount (this invoice)", f"₹{float(payout.get('payout_amount') or 0):,.2f}"],
        ["Sent to (UPI)", payout.get("payout_account_upi_id") or "Not set by business yet"],
    ]
    table = Table(data, colWidths=[110 * mm, 62 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5dd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
        ("FONTNAME", (0, 3), (-1, 4), "Helvetica-Bold"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph(
        "This is a Marketing Fee Payout from ROSKYRO to the referring business named above -- the fixed-% "
        "share of Marketing Fees ROSKYRO collected from partners on referrals this business generated during "
        "the stated period. Not a tax invoice.",
        styles["Normal"],
    ))

    doc.build(elements)
    return buf.getvalue()


def render_subscription_renewal_invoice_pdf(charge: dict) -> bytes:
    """Invoice for a business's own subscription renewal payment to
    ROSKYRO -- the opposite money direction from the Marketing Fee Payout
    invoice above (a business pays ROSKYRO here, ROSKYRO doesn't pay the
    business). Only generated once ROSKYRO has confirmed receipt (see
    routers/subscription_renewals.py's confirm_received), same as how a
    Marketing Fee Payout invoice only exists once that payout record is
    created."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()

    generated_at = now()
    status_label = "PAID" if charge.get("status") == "paid" else "PENDING"
    cycle_label = "Annual" if charge.get("billing_cycle") == "yearly" else "Monthly"

    elements = [
        Paragraph("<b>ROSKYRO Healthcare OS</b>", styles["Title"]),
        Paragraph("Subscription Renewal Invoice", styles["Heading2"]),
        Spacer(1, 4 * mm),
        Paragraph(f"Invoice No: <b>{charge.get('invoice_number', '—')}</b>", styles["Normal"]),
        Paragraph(f"Invoice Date: {generated_at.strftime('%d %b %Y')}", styles["Normal"]),
        Paragraph(f"Status: <b>{status_label}</b>" + (f" (paid {charge['paid_at'].strftime('%d %b %Y')})" if charge.get("paid_at") else ""), styles["Normal"]),
        Spacer(1, 6 * mm),
        Paragraph(f"<b>Billed to:</b> {charge.get('org_name') or '—'}", styles["Normal"]),
        Paragraph(f"<b>Period covered:</b> {charge.get('period') or '—'}", styles["Normal"]),
        Spacer(1, 6 * mm),
    ]

    data = [
        ["Description", "Value"],
        ["Plan", charge.get("plan_name") or "—"],
        ["Billing cycle", cycle_label],
        ["Renewal amount (this invoice)", f"₹{float(charge.get('amount') or 0):,.2f}"],
        ["Payment reference", charge.get("payment_reference") or "—"],
    ]
    table = Table(data, colWidths=[110 * mm, 62 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f2a4a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d5dd")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fc")]),
        ("FONTNAME", (0, 2), (-1, 3), "Helvetica-Bold"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10 * mm))
    elements.append(Paragraph(
        "This is a subscription renewal payment receipt from the business named above to ROSKYRO, for the "
        "ROSKYRO plan and period stated. Not a tax invoice.",
        styles["Normal"],
    ))

    doc.build(elements)
    return buf.getvalue()

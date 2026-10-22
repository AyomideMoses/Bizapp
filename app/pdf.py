from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from . import config
from .utils import WAT

base = getSampleStyleSheet()["Normal"]
small = ParagraphStyle("small", parent=base, fontSize=8, textColor=colors.grey)
title_style = ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=20, alignment=2)
biz_style = ParagraphStyle("biz", parent=base, fontName="Helvetica-Bold", fontSize=14)
bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold")
heading = ParagraphStyle("heading", parent=base, fontName="Helvetica-Bold", fontSize=11, spaceBefore=8, spaceAfter=4)

SERVICE_LABELS = {
    "wash": "Wash",
    "iron": "Iron",
    "wash_iron": "Wash & Iron",
    "dry_clean": "Dry clean",
}
STATUS_LABELS = {"paid": "PAID", "part_paid": "PART PAID", "unpaid": "UNPAID",
                 "carried_forward": "CARRIED FORWARD"}
STATUS_COLORS = {"paid": colors.green, "part_paid": colors.orange, "unpaid": colors.red,
                 "carried_forward": colors.HexColor("#5b21b6")}

def naira(amount: int) -> str:
    # "NGN" is used because the built-in PDF fonts don't include the ₦ symbol
    return f"NGN {amount:,}"

def stamp(dt) -> str:
    return (dt + WAT).strftime("%d %b %Y, %I:%M %p")   # UTC -> Nigerian time

LOGO = Path(__file__).parent / "static" / "logo.png"

def logo_image(height=24 * mm):
    if not LOGO.exists():
        return None
    w, h = ImageReader(str(LOGO)).getSize()
    image = Image(str(LOGO), width=height * w / h, height=height)
    image.hAlign = "LEFT"
    return image

def header(title: str):
    logo = logo_image()
    left = [logo, Spacer(1, 4)] if logo else [Paragraph(escape(config.BUSINESS_NAME), biz_style)]
    left += [
        Paragraph(escape(config.BUSINESS_ADDRESS), small),
        Paragraph(escape(config.BUSINESS_PHONE), small),
    ]
    table = Table([[left, Paragraph(title, title_style)]], colWidths=[100 * mm, 70 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))
    return [table, Spacer(1, 8)]   
    
    table = Table([[left, Paragraph(title, title_style)]], colWidths=[100 * mm, 70 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
    ]))
    return [table, Spacer(1, 8)]

def info_table(rows):
    table = Table(rows, colWidths=[35 * mm, 135 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table

def build(story) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    doc.build(story)
    return buf.getvalue()

def invoice_pdf(invoice) -> bytes:
    order, customer = invoice.order, invoice.order.customer
    story = header("INVOICE")

    rows = [
        ["Invoice no:", invoice.invoice_number],
        ["Date:", stamp(invoice.created_at)],
        ["Order status:", order.status.capitalize()],
    ]
    if order.due_date:
        rows.append(["Due date:", order.due_date.strftime("%d %b %Y, %I:%M %p")])
    story += [info_table(rows), Paragraph("Bill to", heading),
              Paragraph(escape(customer.name), bold),
              Paragraph(escape(customer.phone), base)]
    if customer.address:
        story.append(Paragraph(escape(customer.address), base))
    story.append(Spacer(1, 10))

    data = [["Garment", "Service", "Qty", "Unit price", "Amount"]]
    for item in order.items:
        garment = escape(item.garment)
        if item.notes:
            garment += f"<br/><font size=7 color='grey'>Note: {escape(item.notes)}</font>"
        data.append([
            Paragraph(garment, base),
            SERVICE_LABELS.get(item.service, item.service),
            str(item.quantity),
            naira(item.unit_price),
            naira(item.quantity * item.unit_price),
        ])
    items = Table(data, colWidths=[62 * mm, 30 * mm, 14 * mm, 32 * mm, 32 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
    ]))
    story += [items, Spacer(1, 8)]

    status = invoice.payment_status

    if invoice.carry_ins:
        story.append(Paragraph("Previous unpaid balance brought forward", heading))
        brought = [["From invoice", "Date", "Amount"]]
        for c in sorted(invoice.carry_ins, key=lambda c: c.id):
            old = c.from_invoice
            brought.append([old.invoice_number, (old.created_at + WAT).strftime("%d %b %Y"), naira(c.amount)])
        bt = Table(brought, colWidths=[55 * mm, 45 * mm, 35 * mm])
        bt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fff7e6")),
        ]))
        story += [bt, Spacer(1, 8)]

    rows = [["Items total", naira(invoice.total)]]
    if invoice.carried_in:
        rows.append(["Previous balance", naira(invoice.carried_in)])
        rows.append(["Total due", naira(invoice.amount_due)])
    if invoice.carried_out:
        rows.append(["Carried forward", "- " + naira(invoice.carried_out)])
    rows.append(["Amount paid", naira(invoice.amount_paid)])
    rows.append(["Balance due", naira(invoice.balance)])
    last = len(rows) - 1
    totals = Table(rows, colWidths=[45 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
        ("LINEABOVE", (0, last), (-1, last), 0.5, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    story += [totals, Spacer(1, 6)]

    status_style = ParagraphStyle("status", parent=bold, fontSize=14, alignment=2,
                                  textColor=STATUS_COLORS[status])
    story.append(Paragraph(STATUS_LABELS[status], status_style))

    if invoice.carry_outs:
        targets = ", ".join(sorted({c.to_invoice.invoice_number for c in invoice.carry_outs}))
        story.append(Paragraph(
            escape(f"The unpaid balance of {naira(invoice.carried_out)} was carried forward to {targets}."),
            small,
        ))
    if invoice.payments:
        story.append(Paragraph("Payments received", heading))
        pay = [["Date", "Method", "Reference", "Amount"]]
        for p in sorted(invoice.payments, key=lambda p: p.id):
            pay.append([stamp(p.paid_at), p.method.capitalize(), p.reference or "-", naira(p.amount)])
        pt = Table(pay, colWidths=[55 * mm, 30 * mm, 50 * mm, 35 * mm])
        pt.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
        ]))
        story.append(pt)

    story += [Spacer(1, 16), Paragraph(escape(config.FOOTER_NOTE), small)]
    return build(story)

def receipt_pdf(payment) -> bytes:
    invoice = payment.invoice
    customer = invoice.order.customer
    paid_so_far = sum(p.amount for p in invoice.payments if p.id <= payment.id)
    balance_after = invoice.payable - paid_so_far

    story = header("RECEIPT")
    story.append(info_table([
        ["Receipt no:", f"RCT-{payment.id:05d}"],
        ["Date:", stamp(payment.paid_at)],
        ["Invoice no:", invoice.invoice_number],
        ["Received from:", customer.name],
        ["Payment method:", payment.method.capitalize()],
        ["Reference:", payment.reference or "-"],
    ]))
    story.append(Spacer(1, 14))

    amount_style = ParagraphStyle("amount", parent=bold, fontSize=18)
    box = Table([
        [Paragraph("Amount received", base), Paragraph(naira(payment.amount), amount_style)],
        ["Invoice total", naira(invoice.amount_due)],
        ["Balance after this payment", naira(balance_after)],
    ], colWidths=[85 * mm, 85 * mm])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(box)

    label, color = ("FULLY PAID", colors.green) if balance_after == 0 else ("BALANCE OUTSTANDING", colors.orange)
    story += [Spacer(1, 8),
              Paragraph(label, ParagraphStyle("rs", parent=bold, fontSize=12, alignment=2, textColor=color)),
              Spacer(1, 16), Paragraph(escape(config.FOOTER_NOTE), small)]
    return build(story)

8
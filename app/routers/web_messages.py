from urllib.parse import quote
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .. import config, models
from ..database import SessionLocal, get_db
from ..utils import WAT, now_wat
from .web import templates, web_user

KINDS = {
    "received": "Order received",
    "ready": "Ready for pickup",
    "receipt": "Payment receipt",
    "balance": "Balance reminder",
    "delayed": "Delay notice",
}

class SafeDict(dict):
    """Leaves unknown {placeholders} untouched instead of crashing."""
    def __missing__(self, key):
        return "{" + key + "}"

def whatsapp_number(raw):
    """Turn a saved phone number into international digits for wa.me, or None."""
    raw = (raw or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    cc = config.COUNTRY_CODE
    if raw.startswith("+"):
        number = digits
    elif digits.startswith(cc) and len(digits) == len(cc) + 10:
        number = digits
    elif digits.startswith("0") and len(digits) == 11:
        number = cc + digits[1:]
    elif len(digits) == 10:
        number = cc + digits
    else:
        return None
    return number if 8 <= len(number) <= 15 else None

def naira(n) -> str:
    return f"₦{int(n):,}"

def build_values(order) -> dict:
    invoice = order.invoice
    balance = invoice.balance if invoice else 0
    latest = max(invoice.payments, key=lambda p: p.id) if invoice and invoice.payments else None
    items = ", ".join(f"{i.quantity} {i.garment}" for i in order.items[:5])
    if len(order.items) > 5:
        items += ", ..."
    return {
        "name": order.customer.name,
        "business": config.BUSINESS_NAME,
        "invoice": invoice.invoice_number if invoice else f"#{order.id}",
        "total": naira(invoice.amount_due) if invoice else "",        "paid": naira(invoice.amount_paid) if invoice else "",
        "balance": naira(balance),
        "balance_line": f"Balance to pay: {naira(balance)}." if balance > 0 else "Your order is fully paid.",
        "amount": naira(latest.amount) if latest else "",
        "items": items,
        "due": order.due_date.strftime("%a %d %b, %I:%M %p") if order.due_date else "soon",
    }

def order_log(order_id: int):
    """Recent messages for an order (used by the order page)."""
    db = SessionLocal()
    try:
        return (db.query(models.Notification).filter_by(order_id=order_id)
                .order_by(models.Notification.id.desc()).limit(10).all())
    finally:
        db.close()

templates.env.globals["order_log"] = order_log
templates.env.globals["kind_labels"] = KINDS

router = APIRouter(include_in_schema=False)

def load(db: Session, order_id: int, kind: str):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if kind not in KINDS or kind not in config.WHATSAPP_TEMPLATES:
        raise HTTPException(404, "Unknown message type")
    if kind == "receipt" and not (order.invoice and order.invoice.payments):
        raise HTTPException(400, "This order has no payment to send a receipt for")
    return order

def form_page(request, user, order, kind, text, error=None, status=200):
    return templates.TemplateResponse(
        request, "message_form.html",
        {"user": user, "page": "reminders", "order": order, "kind": kind,
         "label": KINDS[kind], "text": text, "error": error,
         "number": whatsapp_number(order.customer.phone)},
        status_code=status,
    )

@router.get("/app/orders/{order_id:int}/message/{kind}")
def message_page(request: Request, order_id: int, kind: str, user=Depends(web_user),
                 db: Session = Depends(get_db)):
    order = load(db, order_id, kind)
    text = config.WHATSAPP_TEMPLATES[kind].format_map(SafeDict(build_values(order)))
    return form_page(request, user, order, kind, text)

@router.post("/app/orders/{order_id:int}/message/{kind}")
def message_send(request: Request, order_id: int, kind: str, message: str = Form(""),
                 user=Depends(web_user), db: Session = Depends(get_db)):
    order = load(db, order_id, kind)
    text = message.strip()
    number = whatsapp_number(order.customer.phone)
    if not number:
        return form_page(request, user, order, kind, text,
                         "This customer's phone number can't be used for WhatsApp.", 400)
    if not text:
        return form_page(request, user, order, kind, text, "Write a message first.", 400)
    if len(text) > 1000:
        return form_page(request, user, order, kind, text, "The message is too long (1000 characters at most).", 400)

    db.add(models.Notification(
        order_id=order.id, customer_id=order.customer_id, customer_name=order.customer.name,
        invoice_number=order.invoice.invoice_number if order.invoice else None,
        kind=kind, phone=number, message=text, sent_by=user.username,
    ))
    db.commit()
    return RedirectResponse(f"https://wa.me/{number}?text={quote(text, safe='')}", status_code=303)

@router.get("/app/reminders")
def reminders_page(request: Request, user=Depends(web_user), db: Session = Depends(get_db)):
    last = {}
    for n in db.query(models.Notification).filter_by(kind="balance").order_by(models.Notification.id):
        last[n.order_id] = n.created_at

    today = (now_wat()).date()
    rows = []
    for invoice in db.query(models.Invoice).order_by(models.Invoice.created_at).all():
        if invoice.balance > 0:
            order = invoice.order
            rows.append({
                "order_id": order.id,
                "invoice_number": invoice.invoice_number,
                "customer_id": order.customer.id,
                "customer_name": order.customer.name,
                "phone": order.customer.phone,
                "balance": invoice.balance,
                "days": (today - (invoice.created_at + WAT).date()).days,
                "last": last.get(order.id),
            })
    return templates.TemplateResponse(
        request, "reminders.html",
        {"user": user, "page": "reminders", "rows": rows,
         "total": sum(r["balance"] for r in rows)},
    )

@router.get("/app/messages")
def messages_page(request: Request, user=Depends(web_user), db: Session = Depends(get_db)):
    log = db.query(models.Notification).order_by(models.Notification.id.desc()).limit(200).all()
    return templates.TemplateResponse(
        request, "messages.html", {"user": user, "page": "reminders", "log": log},
    )
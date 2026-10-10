from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from ..utils import now_wat, WAT
from .web import templates, web_user, SERVICES, blank_row, parse_rows

STATUSES = ["received", "processing", "ready", "delivered"]
METHODS = [("cash", "Cash"), ("transfer", "Transfer"), ("pos", "POS")]
METHOD_KEYS = {key for key, _ in METHODS}
MESSAGES = {
    "status": "Status updated.",
    "paid": "Payment recorded.",
    "updated": "Order updated.",
    "payment_updated": "Payment updated.",
    "payment_deleted": "Payment deleted.",
}

def is_overdue(order) -> bool:
    return bool(order.due_date and order.status != "delivered" and order.due_date < now_wat())

# Ready-by times are saved as entered (Nigerian time); payment times are saved in UTC.
templates.env.filters["dt"] = lambda d: d.strftime("%d %b %Y, %I:%M %p") if d else "-"
templates.env.filters["watdt"] = lambda d: (d + WAT).strftime("%d %b %Y, %I:%M %p") if d else "-"
templates.env.globals["is_overdue"] = is_overdue

def web_admin(user=Depends(web_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admins only")
    return user

router = APIRouter(include_in_schema=False)

# ---------- Orders list ----------

@router.get("/app/orders")
def orders_page(request: Request, status: str = "", pay: str = "", q: str = "",
                user=Depends(web_user), db: Session = Depends(get_db)):
    query = (
        db.query(models.Order)
        .join(models.Customer, models.Customer.id == models.Order.customer_id)
        .outerjoin(models.Invoice, models.Invoice.order_id == models.Order.id)
    )
    if status in STATUSES:
        query = query.filter(models.Order.status == status)
    term = q.strip()
    if term:
        query = query.filter(
            models.Customer.name.ilike(f"%{term}%")
            | models.Customer.phone.contains(term)
            | models.Invoice.invoice_number.ilike(f"%{term}%")
        )
    orders = query.order_by(models.Order.created_at.desc()).limit(300).all()

    if pay == "unpaid":
        orders = [o for o in orders if o.invoice and o.invoice.balance > 0]
    elif pay == "paid":
        orders = [o for o in orders if o.invoice and o.invoice.balance == 0]

    return templates.TemplateResponse(
        request, "orders.html",
        {"user": user, "page": "orders", "orders": orders, "status": status,
         "pay": pay, "q": term, "statuses": STATUSES},
    )

# ---------- Single order ----------

def order_page(request, user, order, error=None, message=None, status=200, form=None):
    return templates.TemplateResponse(
        request, "order_detail.html",
        {"user": user, "page": "orders", "order": order, "invoice": order.invoice,
         "statuses": STATUSES, "methods": METHODS, "service_labels": dict(SERVICES),
         "error": error, "message": message,
         "form": form or {"amount": "", "method": "cash", "reference": ""}},
        status_code=status,
    )

@router.get("/app/orders/{order_id:int}")
def order_detail(request: Request, order_id: int, msg: str = "",
                 user=Depends(web_user), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order_page(request, user, order, message=MESSAGES.get(msg))

@router.post("/app/orders/{order_id:int}/status")
def set_status(order_id: int, status: str = Form(...), user=Depends(web_user),
               db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    if status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    order.status = status
    db.commit()
    return RedirectResponse(f"/app/orders/{order.id}?msg=status", status_code=303)

@router.post("/app/orders/{order_id:int}/payment")
def add_payment(request: Request, order_id: int, amount: str = Form(""),
                method: str = Form(""), reference: str = Form(""),
                user=Depends(web_user), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order or not order.invoice:
        raise HTTPException(404, "Order not found")
    invoice = order.invoice
    form = {"amount": amount, "method": method or "cash", "reference": reference}

    def fail(message):
        return order_page(request, user, order, error=message, status=400, form=form)

    if invoice.balance == 0:
        return fail("This invoice is already fully paid.")
    try:
        value = int(amount.strip())
    except ValueError:
        return fail("Enter the amount as a whole number of naira.")
    if value < 1:
        return fail("The amount must be more than 0.")
    if value > invoice.balance:
        return fail(f"The amount is more than the balance of ₦{invoice.balance:,}.")
    if method not in METHOD_KEYS:
        return fail("Choose how the customer paid.")

    db.add(models.Payment(invoice_id=invoice.id, amount=value, method=method,
                          reference=reference.strip() or None))
    db.commit()
    return RedirectResponse(f"/app/orders/{order.id}?msg=paid", status_code=303)

# ---------- Admin: edit and delete an order ----------

def edit_form(request, user, db, order, rows, customer_id, due_date, error=None, status=200):
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    label = order.invoice.invoice_number if order.invoice else f"order {order.id}"
    return templates.TemplateResponse(
        request, "order_form.html",
        {"user": user, "page": "orders", "customers": customers, "rows": rows,
         "customer_id": customer_id, "due_date": due_date, "services": SERVICES,
         "error": error, "title": f"Edit {label}",
         "action": f"/app/orders/{order.id}/edit", "submit_label": "Save changes",
         "cancel": f"/app/orders/{order.id}"},
        status_code=status,
    )

@router.get("/app/orders/{order_id:int}/edit")
def order_edit(request: Request, order_id: int, user=Depends(web_admin),
               db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    rows = [
        {"garment": i.garment, "service": i.service, "quantity": str(i.quantity),
         "unit_price": str(i.unit_price), "notes": i.notes or ""}
        for i in order.items
    ] or [blank_row()]
    due = order.due_date.strftime("%Y-%m-%dT%H:%M") if order.due_date else ""
    return edit_form(request, user, db, order, rows, order.customer_id, due)

@router.post("/app/orders/{order_id:int}/edit")
def order_update(
    request: Request,
    order_id: int,
    customer_id: int = Form(0),
    due_date: str = Form(""),
    garment: list[str] = Form([]),
    service: list[str] = Form([]),
    quantity: list[str] = Form([]),
    unit_price: list[str] = Form([]),
    notes: list[str] = Form([]),
    user=Depends(web_admin),
    db: Session = Depends(get_db),
):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    rows = [
        {"garment": g, "service": s, "quantity": q, "unit_price": p, "notes": n}
        for g, s, q, p, n in zip(garment, service, quantity, unit_price, notes)
    ] or [blank_row()]

    def fail(message):
        return edit_form(request, user, db, order, rows, customer_id, due_date, message, status=400)

    customer = db.get(models.Customer, customer_id)
    if not customer:
        return fail("Choose a customer.")

    due = None
    if due_date.strip():
        try:
            due = datetime.strptime(due_date.strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            return fail("The ready-by date is not valid.")

    items, error = parse_rows(rows)
    if error:
        return fail(error)

    new_total = sum(i["quantity"] * i["unit_price"] for i in items)
    if order.invoice and new_total < order.invoice.amount_paid:
        return fail(
            f"The new total (₦{new_total:,}) is less than the ₦{order.invoice.amount_paid:,} "
            "already paid. Edit or delete the payments first."
        )

    order.customer_id = customer.id
    order.due_date = due
    order.items.clear()
    for item in items:
        order.items.append(models.OrderItem(**item))
    if order.invoice:
        order.invoice.total = new_total
    db.commit()
    return RedirectResponse(f"/app/orders/{order.id}?msg=updated", status_code=303)

@router.post("/app/orders/{order_id:int}/delete")
def order_delete(order_id: int, user=Depends(web_admin), db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    customer_id = order.customer_id
    if order.invoice:
        db.delete(order.invoice)      # its payments are deleted with it
    db.delete(order)                  # its garments are deleted with it
    db.commit()
    return RedirectResponse(f"/app/customers/{customer_id}?msg=order_deleted", status_code=303)

# ---------- Admin: edit and delete a payment ----------

def payment_page(request, user, payment, form, error=None, status=200):
    return templates.TemplateResponse(
        request, "payment_form.html",
        {"user": user, "page": "orders", "payment": payment, "invoice": payment.invoice,
         "methods": METHODS, "form": form, "error": error},
        status_code=status,
    )

@router.get("/app/payments/{payment_id:int}/edit")
def payment_edit(request: Request, payment_id: int, user=Depends(web_admin),
                 db: Session = Depends(get_db)):
    payment = db.get(models.Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    form = {"amount": str(payment.amount), "method": payment.method,
            "reference": payment.reference or ""}
    return payment_page(request, user, payment, form)

@router.post("/app/payments/{payment_id:int}/edit")
def payment_update(request: Request, payment_id: int, amount: str = Form(""),
                   method: str = Form(""), reference: str = Form(""),
                   user=Depends(web_admin), db: Session = Depends(get_db)):
    payment = db.get(models.Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    invoice = payment.invoice
    form = {"amount": amount, "method": method or payment.method, "reference": reference}

    def fail(message):
        return payment_page(request, user, payment, form, error=message, status=400)

    try:
        value = int(amount.strip())
    except ValueError:
        return fail("Enter the amount as a whole number of naira.")
    if value < 1:
        return fail("The amount must be more than 0.")
    room = invoice.total - (invoice.amount_paid - payment.amount)
    if value > room:
        return fail(f"The most this payment can be is ₦{room:,}.")
    if method not in METHOD_KEYS:
        return fail("Choose how the customer paid.")

    payment.amount = value
    payment.method = method
    payment.reference = reference.strip() or None
    db.commit()
    return RedirectResponse(f"/app/orders/{invoice.order_id}?msg=payment_updated", status_code=303)

@router.post("/app/payments/{payment_id:int}/delete")
def payment_delete(payment_id: int, user=Depends(web_admin), db: Session = Depends(get_db)):
    payment = db.get(models.Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    order_id = payment.invoice.order_id
    db.delete(payment)
    db.commit()
    return RedirectResponse(f"/app/orders/{order_id}?msg=payment_deleted", status_code=303)

# ---------- Admin: delete a customer (only when they have no orders) ----------

@router.post("/app/customers/{customer_id:int}/delete")
def customer_delete(customer_id: int, user=Depends(web_admin), db: Session = Depends(get_db)):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    if customer.orders:
        raise HTTPException(400, "Delete this customer's orders first")
    db.delete(customer)
    db.commit()
    return RedirectResponse("/app/customers", status_code=303)
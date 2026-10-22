from datetime import datetime, timedelta
from .orders import next_invoice_number
from .invoices import build_detail
from pathlib import Path
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .. import config, models, ratelimit, debts
from ..database import get_db
from ..security import verify_password, create_token, user_from_token
from ..utils import WAT, now_wat
from . import dashboard as dash

BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.filters["naira"] = lambda v: f"₦{int(v or 0):,}"
templates.env.filters["wat"] = lambda d: (d + WAT).strftime("%d %b %Y") if d else "-"
templates.env.globals["business"] = config.BUSINESS_NAME

class LoginRedirect(Exception):
    """Raised when a page is opened without a valid login."""

def web_user(request: Request, db: Session = Depends(get_db)):
    user = user_from_token(request.cookies.get("token"), db)
    if not user:
        raise LoginRedirect()
    return user

router = APIRouter(include_in_schema=False)

# ---------- Login / logout / dashboard ----------

@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if user_from_token(request.cookies.get("token"), db):
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})

@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...),
          db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(username=username.strip().lower()).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Incorrect username or password"}, status_code=401
        )
    response = RedirectResponse("/app", status_code=303)
    response.set_cookie(
        "token", create_token(user.id),
        max_age=config.TOKEN_HOURS * 3600, httponly=True, samesite="lax",
    )
    return response

@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("token")
    return response

@router.get("/app")
def home(request: Request, user=Depends(web_user), db: Session = Depends(get_db)):
    data = dash.dashboard(db)
    if user.role != "admin":      # staff don't see money figures
        data = {"orders_by_status": data["orders_by_status"],
                "overdue_orders": data["overdue_orders"]}
    hour = now_wat().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    recent = db.query(models.Order).order_by(models.Order.created_at.desc()).limit(5).all()
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"user": user, "data": data, "page": "dashboard", "greeting": greeting, "recent": recent},
    )
    
# ---------- Customers ----------

MESSAGES = {
    "created": "Customer added.",
    "updated": "Customer updated.",
    "order": "Order created and invoice generated.",
    "order_deleted": "Order deleted.",
}

def clean_phone(raw: str) -> str:
    return "".join(ch for ch in raw if ch.isdigit() or ch == "+")

def validate_customer(db: Session, name: str, phone: str, address: str, exclude_id=None):
    """Return (clean_values, None) or (None, error_message)."""
    name, address, phone = name.strip(), address.strip(), clean_phone(phone)
    if not name:
        return None, "Name is required."
    if sum(ch.isdigit() for ch in phone) < 7:
        return None, "Enter a valid phone number."
    other = db.query(models.Customer).filter_by(phone=phone).first()
    if other and other.id != exclude_id:
        return None, f"{other.name} already uses this phone number."
    return {"name": name, "phone": phone, "address": address or None}, None

def customer_form(request, user, title, action, values, error=None, status=200, cancel="/app/customers"):
    return templates.TemplateResponse(
        request, "customer_form.html",
        {"user": user, "page": "customers", "title": title, "action": action,
         "values": values, "error": error, "cancel": cancel},
        status_code=status,
    )

@router.get("/app/customers")
def customers_page(request: Request, q: str = "", user=Depends(web_user),
                   db: Session = Depends(get_db)):
    query = db.query(models.Customer)
    term = q.strip()
    if term:
        query = query.filter(
            models.Customer.name.ilike(f"%{term}%") | models.Customer.phone.contains(term)
        )
    customers = query.order_by(models.Customer.name).all()
    return templates.TemplateResponse(
        request, "customers.html",
        {"user": user, "page": "customers", "customers": customers, "q": term},
    )

@router.get("/app/customers/new")
def customer_new(request: Request, user=Depends(web_user)):
    return customer_form(request, user, "Add customer", "/app/customers/new",
                         {"name": "", "phone": "", "address": ""})

@router.post("/app/customers/new")
def customer_create(request: Request, name: str = Form(""), phone: str = Form(""),
                    address: str = Form(""), user=Depends(web_user),
                    db: Session = Depends(get_db)):
    clean, error = validate_customer(db, name, phone, address)
    if error:
        return customer_form(request, user, "Add customer", "/app/customers/new",
                             {"name": name, "phone": phone, "address": address},
                             error, status=400)
    customer = models.Customer(**clean)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return RedirectResponse(f"/app/customers/{customer.id}?msg=created", status_code=303)

@router.get("/app/customers/{customer_id}")
def customer_detail(request: Request, customer_id: int, msg: str = "",
                    user=Depends(web_user), db: Session = Depends(get_db)):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    orders = sorted(customer.orders, key=lambda o: o.created_at, reverse=True)
    invoices = [o.invoice for o in orders if o.invoice]
    return templates.TemplateResponse(
        request, "customer_detail.html",
        {"user": user, "page": "customers", "customer": customer, "orders": orders,
         "billed": sum(i.total for i in invoices),
         "paid": sum(i.amount_paid for i in invoices),
         "balance": sum(i.balance for i in invoices),
         "message": MESSAGES.get(msg)},
    )

@router.get("/app/customers/{customer_id}/edit")
def customer_edit(request: Request, customer_id: int, user=Depends(web_user),
                  db: Session = Depends(get_db)):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer_form(
        request, user, "Edit customer", f"/app/customers/{customer.id}/edit",
        {"name": customer.name, "phone": customer.phone, "address": customer.address or ""},
        cancel=f"/app/customers/{customer.id}",
    )

@router.post("/app/customers/{customer_id}/edit")
def customer_update(request: Request, customer_id: int, name: str = Form(""),
                    phone: str = Form(""), address: str = Form(""),
                    user=Depends(web_user), db: Session = Depends(get_db)):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    clean, error = validate_customer(db, name, phone, address, exclude_id=customer.id)
    if error:
        return customer_form(
            request, user, "Edit customer", f"/app/customers/{customer.id}/edit",
            {"name": name, "phone": phone, "address": address},
            error, status=400, cancel=f"/app/customers/{customer.id}",
        )
    customer.name, customer.phone, customer.address = clean["name"], clean["phone"], clean["address"]
    db.commit()
    return RedirectResponse(f"/app/customers/{customer.id}?msg=updated", status_code=303)

# ---------- New order ----------

SERVICES = [("wash", "Wash"), ("iron", "Iron"), ("wash_iron", "Wash & Iron"), ("dry_clean", "Dry clean")]
SERVICE_KEYS = {key for key, _ in SERVICES}

def blank_row():
    return {"garment": "", "service": "wash_iron", "quantity": "1", "unit_price": "", "notes": ""}
def parse_local_received(text):
    """Parse a 'received on' value (Nigerian time). Returns (local_datetime, error)."""
    try:
        local = datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M")
    except ValueError:
        return None, "The received date is not valid."
    if local > now_wat() + timedelta(minutes=5):
        return None, "The received date can't be in the future."
    if local.year < 2020:
        return None, "The received date is too far in the past."
    return local, None

def parse_received(text, user):
    """For new orders. Returns (utc_datetime_or_None, backdated, error).
    None means 'use the real time'. Only admins can set a date."""
    if user.role != "admin" or not text.strip():
        return None, False, None
    local, error = parse_local_received(text)
    if error:
        return None, False, error
    if local >= now_wat() - timedelta(minutes=10):
        return None, False, None          # effectively "now"
    return local - WAT, True, None
def order_form(request, user, db, rows, customer_id=0, due_date="", error=None, status=200,
               received=None):
    customers = db.query(models.Customer).order_by(models.Customer.name).all()
    now_text = now_wat().strftime("%Y-%m-%dT%H:%M")
    return templates.TemplateResponse(
        request, "order_form.html",
        {"user": user, "page": "new_order", "customers": customers, "rows": rows,
         "customer_id": customer_id, "due_date": due_date, "services": SERVICES, "error": error,
         "debts": debts.debts_by_customer(db),
         "can_backdate": user.role == "admin",
         "received": received if received is not None else now_text,
         "received_default": now_text},
        status_code=status,
    )

def parse_rows(raw_rows):
    """Return (items, None) or (None, error_message). Fully blank rows are skipped."""
    items = []
    for number, row in enumerate(raw_rows, start=1):
        garment, price_text = row["garment"].strip(), row["unit_price"].strip()
        if not garment and not price_text:
            continue
        label = f"Item {number}"
        if not garment:
            return None, f"{label}: enter the garment name."
        if row["service"] not in SERVICE_KEYS:
            return None, f"{label}: choose a service."
        try:
            quantity = int(row["quantity"])
            price = int(price_text)
        except ValueError:
            return None, f"{label}: quantity and price must be whole numbers."
        if not 1 <= quantity <= 500:
            return None, f"{label}: quantity must be between 1 and 500."
        if not 1 <= price <= 10_000_000:
            return None, f"{label}: price must be a whole number above 0."
        items.append({"garment": garment, "service": row["service"], "quantity": quantity,
                      "unit_price": price, "notes": row["notes"].strip() or None})
    if not items:
        return None, "Add at least one garment."
    return items, None

@router.get("/app/orders/new")
def order_new(request: Request, customer_id: int = 0, user=Depends(web_user),
              db: Session = Depends(get_db)):
    return order_form(request, user, db, [blank_row()], customer_id)

@router.post("/app/orders/new")
def order_create(
    request: Request,
    customer_id: int = Form(0),
    due_date: str = Form(""),
    received: str = Form(""),
    carry_forward: str = Form(""),
    garment: list[str] = Form([]),
    service: list[str] = Form([]),
    quantity: list[str] = Form([]),
    unit_price: list[str] = Form([]),
    notes: list[str] = Form([]),
    user=Depends(web_user),
    db: Session = Depends(get_db),
):
    rows = [
        {"garment": g, "service": s, "quantity": q, "unit_price": p, "notes": n}
        for g, s, q, p, n in zip(garment, service, quantity, unit_price, notes)
    ] or [blank_row()]

    def fail(message):
        return order_form(request, user, db, rows, customer_id, due_date, message,
                          status=400, received=received or None)

    customer = db.get(models.Customer, customer_id)
    if not customer:
        return fail("Choose a customer.")

    received_utc, backdated, error = parse_received(received, user)
    if error:
        return fail(error)

    due = None
    if due_date.strip():
        try:
            due = datetime.strptime(due_date.strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            return fail("The ready-by date is not valid.")
    if due and received_utc and due < received_utc + WAT:
        return fail("The ready-by time can't be before the received date.")

    items, error = parse_rows(rows)
    if error:
        return fail(error)

    order = models.Order(customer_id=customer.id, due_date=due)
    if received_utc:
        order.created_at = received_utc
    for item in items:
        order.items.append(models.OrderItem(**item))
    invoice = models.Invoice(
        invoice_number=next_invoice_number(db),
        total=sum(i["quantity"] * i["unit_price"] for i in items),
    )
    if received_utc:
        invoice.created_at = received_utc
    order.invoice = invoice

    if carry_forward == "1" and not backdated:
        for old in debts.open_invoices(db, customer.id):
            db.add(models.CarryForward(from_invoice=old, to_invoice=invoice, amount=old.balance))
    db.add(order)
    db.commit()
    return RedirectResponse(f"/app/customers/{customer.id}?msg=order", status_code=303)
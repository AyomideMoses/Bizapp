from datetime import date, timedelta
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from .. import backup, models
from ..database import get_db
from ..security import hash_password
from ..utils import today_wat
from . import dashboard as dash
from .web import templates
from .web_orders import web_admin

router = APIRouter(include_in_schema=False)

MESSAGES = {
    "expense_added": "Expense added.",
    "expense_updated": "Expense updated.",
    "expense_deleted": "Expense deleted.",
    "user_added": "User created.",
    "user_updated": "User updated.",
    "user_deleted": "User deleted.",
    "password_reset": "Password updated.",
    "backup_created": "Backup created.",
    "backup_deleted": "Backup deleted.",
}

def parse_day(text, default):
    try:
        return date.fromisoformat(text.strip()) if text and text.strip() else default
    except ValueError:
        return default

# =====================================================================
# Expenses
# =====================================================================

def validate_expense(category, description, amount, day):
    cat = category.strip().lower()
    if not cat:
        return None, "Choose or type a category."
    if len(cat) > 40:
        return None, "The category is too long (40 characters at most)."
    try:
        value = int(amount.strip())
    except ValueError:
        return None, "Enter the amount as a whole number of naira."
    if not 1 <= value <= 100_000_000:
        return None, "The amount must be between ₦1 and ₦100,000,000."
    try:
        when = date.fromisoformat(day.strip()) if day.strip() else today_wat()
    except ValueError:
        return None, "The date is not valid."
    return {"category": cat, "description": description.strip() or None,
            "amount": value, "expense_date": when}, None

def expense_form(request, user, db, title, action, values, error=None, status=200):
    categories = [c for (c,) in db.query(models.Expense.category).distinct().order_by(models.Expense.category)]
    return templates.TemplateResponse(
        request, "expense_form.html",
        {"user": user, "page": "expenses", "title": title, "action": action,
         "values": values, "error": error, "categories": categories},
        status_code=status,
    )

@router.get("/app/expenses")
def expenses_page(request: Request, category: str = "", start: str = "", end: str = "",
                  msg: str = "", user=Depends(web_admin), db: Session = Depends(get_db)):
    query = db.query(models.Expense)
    cat = category.strip().lower()
    if cat:
        query = query.filter(models.Expense.category == cat)
    s, e = parse_day(start, None), parse_day(end, None)
    if s:
        query = query.filter(models.Expense.expense_date >= s)
    if e:
        query = query.filter(models.Expense.expense_date <= e)
    expenses = query.order_by(models.Expense.expense_date.desc(), models.Expense.id.desc()).limit(500).all()
    categories = [c for (c,) in db.query(models.Expense.category).distinct().order_by(models.Expense.category)]
    return templates.TemplateResponse(
        request, "expenses.html",
        {"user": user, "page": "expenses", "expenses": expenses, "total": sum(x.amount for x in expenses),
         "categories": categories, "category": cat, "start": start, "end": end,
         "message": MESSAGES.get(msg)},
    )

@router.get("/app/expenses/new")
def expense_new(request: Request, user=Depends(web_admin), db: Session = Depends(get_db)):
    values = {"category": "", "description": "", "amount": "", "expense_date": today_wat().isoformat()}
    return expense_form(request, user, db, "Add expense", "/app/expenses/new", values)

@router.post("/app/expenses/new")
def expense_create(request: Request, category: str = Form(""), description: str = Form(""),
                   amount: str = Form(""), expense_date: str = Form(""),
                   user=Depends(web_admin), db: Session = Depends(get_db)):
    clean, error = validate_expense(category, description, amount, expense_date)
    if error:
        values = {"category": category, "description": description, "amount": amount,
                  "expense_date": expense_date}
        return expense_form(request, user, db, "Add expense", "/app/expenses/new", values, error, 400)
    db.add(models.Expense(**clean))
    db.commit()
    return RedirectResponse("/app/expenses?msg=expense_added", status_code=303)

@router.get("/app/expenses/{expense_id:int}/edit")
def expense_edit(request: Request, expense_id: int, user=Depends(web_admin),
                 db: Session = Depends(get_db)):
    expense = db.get(models.Expense, expense_id)
    if not expense:
        raise HTTPException(404, "Expense not found")
    values = {"category": expense.category, "description": expense.description or "",
              "amount": str(expense.amount), "expense_date": expense.expense_date.isoformat()}
    return expense_form(request, user, db, "Edit expense", f"/app/expenses/{expense.id}/edit", values)

@router.post("/app/expenses/{expense_id:int}/edit")
def expense_update(request: Request, expense_id: int, category: str = Form(""),
                   description: str = Form(""), amount: str = Form(""), expense_date: str = Form(""),
                   user=Depends(web_admin), db: Session = Depends(get_db)):
    expense = db.get(models.Expense, expense_id)
    if not expense:
        raise HTTPException(404, "Expense not found")
    clean, error = validate_expense(category, description, amount, expense_date)
    if error:
        values = {"category": category, "description": description, "amount": amount,
                  "expense_date": expense_date}
        return expense_form(request, user, db, "Edit expense", f"/app/expenses/{expense.id}/edit",
                            values, error, 400)
    for key, value in clean.items():
        setattr(expense, key, value)
    db.commit()
    return RedirectResponse("/app/expenses?msg=expense_updated", status_code=303)

@router.post("/app/expenses/{expense_id:int}/delete")
def expense_delete(expense_id: int, user=Depends(web_admin), db: Session = Depends(get_db)):
    expense = db.get(models.Expense, expense_id)
    if not expense:
        raise HTTPException(404, "Expense not found")
    db.delete(expense)
    db.commit()
    return RedirectResponse("/app/expenses?msg=expense_deleted", status_code=303)

# =====================================================================
# Users
# =====================================================================

def password_error(password: str):
    if not 8 <= len(password) <= 64:
        return "The password must be 8 to 64 characters."
    if len(password.encode()) > 72:
        return "The password is too long. Use fewer special characters."
    return None

def user_page(request, user, mode, target=None, values=None, error=None, status=200):
    if mode == "create":
        title, action = "Add user", "/app/users/new"
        values = values or {"username": "", "full_name": "", "role": "staff"}
    else:
        title, action = f"Edit {target.username}", f"/app/users/{target.id}/edit"
        values = values or {"full_name": target.full_name, "role": target.role,
                            "is_active": "1" if target.is_active else "0"}
    return templates.TemplateResponse(
        request, "user_form.html",
        {"user": user, "page": "users", "mode": mode, "target": target, "values": values,
         "title": title, "action": action, "error": error,
         "is_self": bool(target and target.id == user.id)},
        status_code=status,
    )

@router.get("/app/users")
def users_page(request: Request, msg: str = "", user=Depends(web_admin),
               db: Session = Depends(get_db)):
    users = db.query(models.User).order_by(models.User.username).all()
    return templates.TemplateResponse(
        request, "users.html",
        {"user": user, "page": "users", "users": users, "message": MESSAGES.get(msg)},
    )

@router.get("/app/users/new")
def user_new(request: Request, user=Depends(web_admin)):
    return user_page(request, user, "create")

@router.post("/app/users/new")
def user_create(request: Request, username: str = Form(""), full_name: str = Form(""),
                password: str = Form(""), role: str = Form("staff"),
                user=Depends(web_admin), db: Session = Depends(get_db)):
    name = username.strip().lower()
    values = {"username": username, "full_name": full_name, "role": role}

    def fail(message):
        return user_page(request, user, "create", values=values, error=message, status=400)

    if not 3 <= len(name) <= 30:
        return fail("The username must be 3 to 30 characters.")
    if db.query(models.User).filter_by(username=name).first():
        return fail("That username is already taken.")
    if not full_name.strip():
        return fail("Enter the person's full name.")
    if role not in ("admin", "staff"):
        return fail("Choose a role.")
    error = password_error(password)
    if error:
        return fail(error)

    db.add(models.User(username=name, full_name=full_name.strip(),
                       password_hash=hash_password(password), role=role))
    db.commit()
    return RedirectResponse("/app/users?msg=user_added", status_code=303)

@router.get("/app/users/{user_id:int}/edit")
def user_edit(request: Request, user_id: int, user=Depends(web_admin),
              db: Session = Depends(get_db)):
    target = db.get(models.User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    return user_page(request, user, "edit", target)

@router.post("/app/users/{user_id:int}/edit")
def user_update(request: Request, user_id: int, full_name: str = Form(""),
                role: str = Form(""), is_active: str = Form(""),
                user=Depends(web_admin), db: Session = Depends(get_db)):
    target = db.get(models.User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    is_self = target.id == user.id
    values = {"full_name": full_name, "role": role or target.role,
              "is_active": is_active or ("1" if target.is_active else "0")}

    def fail(message):
        return user_page(request, user, "edit", target, values, message, 400)

    if not full_name.strip():
        return fail("Enter the person's full name.")
    if not is_self:
        if role not in ("admin", "staff"):
            return fail("Choose a role.")
        if is_active not in ("0", "1"):
            return fail("Choose active or deactivated.")
        target.role = role
        target.is_active = is_active == "1"
    target.full_name = full_name.strip()
    db.commit()
    return RedirectResponse("/app/users?msg=user_updated", status_code=303)

@router.post("/app/users/{user_id:int}/password")
def user_password(request: Request, user_id: int, new_password: str = Form(""),
                  user=Depends(web_admin), db: Session = Depends(get_db)):
    target = db.get(models.User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    error = password_error(new_password)
    if error:
        return user_page(request, user, "edit", target, error=error, status=400)
    target.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse("/app/users?msg=password_reset", status_code=303)

@router.post("/app/users/{user_id:int}/delete")
def user_delete(user_id: int, user=Depends(web_admin), db: Session = Depends(get_db)):
    target = db.get(models.User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == user.id:
        raise HTTPException(400, "You cannot delete your own account")
    db.delete(target)
    db.commit()
    return RedirectResponse("/app/users?msg=user_deleted", status_code=303)

# =====================================================================
# Reports
# =====================================================================

@router.get("/app/reports")
def reports_page(request: Request, start: str = "", end: str = "",
                 user=Depends(web_admin), db: Session = Depends(get_db)):
    today = today_wat()
    month_start = today.replace(day=1)
    s = parse_day(start, month_start)
    e = parse_day(end, today)
    error = None
    if s > e:
        error = "The start date must not be after the end date."
        s, e = month_start, today

    last_month_end = month_start - timedelta(days=1)
    ranges = [
        ("Today", today, today),
        ("Last 7 days", today - timedelta(days=6), today),
        ("This month", month_start, today),
        ("Last month", last_month_end.replace(day=1), last_month_end),
        ("This year", date(today.year, 1, 1), today),
    ]
    return templates.TemplateResponse(
        request, "reports.html",
        {"user": user, "page": "reports", "error": error,
         "start": s.isoformat(), "end": e.isoformat(),
         "ranges": [(label, a.isoformat(), b.isoformat()) for label, a, b in ranges],
         "report": dash.revenue_report(start=s, end=e, db=db),
         "outstanding": dash.outstanding_report(db=db),
         "top": dash.top_customers(limit=5, db=db)},
    )

# =====================================================================
# Backups
# =====================================================================

@router.get("/app/backups")
def backups_page(request: Request, msg: str = "", user=Depends(web_admin)):
    return templates.TemplateResponse(
        request, "backups.html",
        {"user": user, "page": "backups", "backups": backup.list_backups(),
         "message": MESSAGES.get(msg)},
    )

@router.post("/app/backups/create")
def backup_create(user=Depends(web_admin)):
    backup.make_backup()
    return RedirectResponse("/app/backups?msg=backup_created", status_code=303)

@router.post("/app/backups/{name}/delete")
def backup_delete(name: str, user=Depends(web_admin)):
    path = backup.find(name)
    if not path:
        raise HTTPException(404, "Backup not found")
    path.unlink()
    return RedirectResponse("/app/backups?msg=backup_deleted", status_code=303)
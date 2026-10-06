from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from ..utils import WAT, now_wat, today_wat, day_range_utc

router = APIRouter(tags=["Dashboard & Reports"])

def revenue_between(db: Session, start: date, end: date) -> int:
    s, e = day_range_utc(start, end)
    return db.query(func.coalesce(func.sum(models.Payment.amount), 0)).filter(
        models.Payment.paid_at >= s, models.Payment.paid_at < e
    ).scalar()

def expenses_between(db: Session, start: date, end: date) -> int:
    return db.query(func.coalesce(func.sum(models.Expense.amount), 0)).filter(
        models.Expense.expense_date >= start, models.Expense.expense_date <= end
    ).scalar()

def outstanding_invoices(db: Session):
    return [inv for inv in db.query(models.Invoice).all() if inv.balance > 0]

@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    today = today_wat()
    month_start = today.replace(day=1)

    s, e = day_range_utc(today, today)
    orders_today = db.query(func.count(models.Order.id)).filter(
        models.Order.created_at >= s, models.Order.created_at < e
    ).scalar()

    by_status = {"received": 0, "processing": 0, "ready": 0, "delivered": 0}
    for status, count in db.query(models.Order.status, func.count(models.Order.id)).group_by(models.Order.status):
        by_status[status] = count

    overdue = db.query(func.count(models.Order.id)).filter(
        models.Order.due_date.isnot(None),
        models.Order.due_date < now_wat(),
        models.Order.status != "delivered",
    ).scalar()

    outstanding = outstanding_invoices(db)
    month_revenue = revenue_between(db, month_start, today)
    month_expenses = expenses_between(db, month_start, today)

    return {
        "today": {
            "date": today,
            "revenue": revenue_between(db, today, today),
            "orders_received": orders_today,
        },
        "orders_by_status": by_status,
        "overdue_orders": overdue,
        "outstanding": {
            "invoices": len(outstanding),
            "total_balance": sum(inv.balance for inv in outstanding),
        },
        "this_month": {
            "revenue": month_revenue,
            "expenses": month_expenses,
            "profit": month_revenue - month_expenses,
        },
    }

@router.get("/reports/revenue")
def revenue_report(
    start: Optional[date] = None,
    end: Optional[date] = None,
    db: Session = Depends(get_db),
):
    today = today_wat()
    start = start or today.replace(day=1)
    end = end or today
    if start > end:
        raise HTTPException(400, "start must not be after end")

    s, e = day_range_utc(start, end)
    payments = db.query(models.Payment).filter(
        models.Payment.paid_at >= s, models.Payment.paid_at < e
    ).all()

    by_day, by_method = {}, {}
    for p in payments:
        day = (p.paid_at + WAT).date().isoformat()
        by_day[day] = by_day.get(day, 0) + p.amount
        by_method[p.method] = by_method.get(p.method, 0) + p.amount

    revenue = sum(p.amount for p in payments)
    expenses = expenses_between(db, start, end)
    return {
        "start": start,
        "end": end,
        "revenue": revenue,
        "expenses": expenses,
        "profit": revenue - expenses,
        "by_day": dict(sorted(by_day.items())),
        "by_method": by_method,
    }

@router.get("/reports/outstanding")
def outstanding_report(db: Session = Depends(get_db)):
    invoices = sorted(outstanding_invoices(db), key=lambda i: i.created_at)
    rows = [
        {
            "invoice_number": inv.invoice_number,
            "customer_name": inv.order.customer.name,
            "customer_phone": inv.order.customer.phone,
            "total": inv.total,
            "amount_paid": inv.amount_paid,
            "balance": inv.balance,
            "payment_status": inv.payment_status,
            "created_at": inv.created_at,
        }
        for inv in invoices
    ]
    return {"total_outstanding": sum(r["balance"] for r in rows), "invoices": rows}

@router.get("/reports/top-customers")
def top_customers(limit: int = 5, db: Session = Depends(get_db)):
    rows = []
    for c in db.query(models.Customer).all():
        invoices = [o.invoice for o in c.orders if o.invoice]
        if invoices:
            rows.append({
                "customer_id": c.id,
                "name": c.name,
                "phone": c.phone,
                "orders": len(invoices),
                "total_billed": sum(i.total for i in invoices),
                "total_paid": sum(i.amount_paid for i in invoices),
            })
    rows.sort(key=lambda r: r["total_billed"], reverse=True)
    return rows[:limit]
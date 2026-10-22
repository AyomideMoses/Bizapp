from sqlalchemy import func
from . import models

def open_invoices(db, customer_id):
    """A customer's invoices that still have a balance, oldest first."""
    invoices = (
        db.query(models.Invoice)
        .join(models.Order, models.Order.id == models.Invoice.order_id)
        .filter(models.Order.customer_id == customer_id)
        .order_by(models.Invoice.created_at)
        .all()
    )
    return [i for i in invoices if i.balance > 0]

def debts_by_customer(db):
    """{customer_id: {"total": n, "invoices": [{"number": ..., "balance": ...}]}}"""
    paid = dict(db.query(models.Payment.invoice_id, func.sum(models.Payment.amount))
                .group_by(models.Payment.invoice_id).all())
    cin = dict(db.query(models.CarryForward.to_invoice_id, func.sum(models.CarryForward.amount))
               .group_by(models.CarryForward.to_invoice_id).all())
    cout = dict(db.query(models.CarryForward.from_invoice_id, func.sum(models.CarryForward.amount))
                .group_by(models.CarryForward.from_invoice_id).all())
    rows = (
        db.query(models.Invoice.id, models.Invoice.invoice_number, models.Invoice.total,
                 models.Order.customer_id)
        .join(models.Order, models.Order.id == models.Invoice.order_id)
        .order_by(models.Invoice.created_at)
        .all()
    )
    result = {}
    for invoice_id, number, total, customer_id in rows:
        balance = total + (cin.get(invoice_id) or 0) - (cout.get(invoice_id) or 0) - (paid.get(invoice_id) or 0)
        if balance > 0:
            entry = result.setdefault(customer_id, {"total": 0, "invoices": []})
            entry["total"] += balance
            entry["invoices"].append({"number": number, "balance": balance})
    return result
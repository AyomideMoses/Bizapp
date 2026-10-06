from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..pdf import invoice_pdf

router = APIRouter(prefix="/invoices", tags=["Invoices"])

def build_detail(invoice: models.Invoice) -> dict:
    order = invoice.order
    return {
        "invoice_number": invoice.invoice_number,
        "date": invoice.created_at,
        "customer_name": order.customer.name,
        "customer_phone": order.customer.phone,
        "status": order.status,
        "due_date": order.due_date,
        "items": order.items,
        "total": invoice.total,
        "amount_paid": invoice.amount_paid,
        "balance": invoice.balance,
        "payment_status": invoice.payment_status,
        "payments": invoice.payments,
    }

@router.get("/", response_model=list[schemas.InvoiceOut])
def list_invoices(db: Session = Depends(get_db)):
    return db.query(models.Invoice).order_by(models.Invoice.created_at.desc()).all()

@router.get("/{invoice_number}/pdf")
def download_invoice(invoice_number: str, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).filter_by(invoice_number=invoice_number).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    return Response(
        content=invoice_pdf(invoice),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{invoice_number}.pdf"'},
    )
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..pdf import receipt_pdf

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.post("/", response_model=schemas.PaymentOut)
def record_payment(data: schemas.PaymentCreate, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).filter_by(invoice_number=data.invoice_number).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    if invoice.balance == 0:
        raise HTTPException(400, "This invoice is already fully paid")
    if data.amount > invoice.balance:
        raise HTTPException(400, f"Amount exceeds the balance of ₦{invoice.balance}")

    payment = models.Payment(
        invoice_id=invoice.id,
        amount=data.amount,
        method=data.method,
        reference=data.reference,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment

@router.get("/", response_model=list[schemas.PaymentOut])
def list_payments(invoice_number: str = "", db: Session = Depends(get_db)):
    q = db.query(models.Payment)
    if invoice_number:
        q = q.join(models.Invoice).filter(models.Invoice.invoice_number == invoice_number)
    return q.order_by(models.Payment.paid_at.desc()).all()

@router.get("/{payment_id}/receipt")
def download_receipt(payment_id: int, db: Session = Depends(get_db)):
    payment = db.get(models.Payment, payment_id)
    if not payment:
        raise HTTPException(404, "Payment not found")
    return Response(
        content=receipt_pdf(payment),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="RCT-{payment.id:05d}.pdf"'},
    )
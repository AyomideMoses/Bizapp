from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/orders", tags=["Orders"])

def next_invoice_number(db: Session) -> str:
    year = datetime.utcnow().year
    prefix = f"INV-{year}-"
    numbers = []
    for (number,) in db.query(models.Invoice.invoice_number).filter(
        models.Invoice.invoice_number.like(f"{prefix}%")
    ):
        tail = number.rsplit("-", 1)[1]
        if tail.isdigit():
            numbers.append(int(tail))
    return f"{prefix}{(max(numbers) if numbers else 0) + 1:04d}"
    year = datetime.utcnow().year
    count = (
        db.query(models.Invoice)
        .filter(models.Invoice.invoice_number.like(f"INV-{year}-%"))
        .count()
    )
    return f"INV-{year}-{count + 1:04d}"

@router.post("/", response_model=schemas.OrderOut)
def create_order(data: schemas.OrderCreate, db: Session = Depends(get_db)):
    if not db.get(models.Customer, data.customer_id):
        raise HTTPException(404, "Customer not found")

    order = models.Order(customer_id=data.customer_id, due_date=data.due_date)
    for item in data.items:
        order.items.append(models.OrderItem(**item.model_dump()))

    total = sum(i.quantity * i.unit_price for i in data.items)
    order.invoice = models.Invoice(
        invoice_number=next_invoice_number(db),
        total=total,
    )

    db.add(order)
    db.commit()
    db.refresh(order)
    return order

@router.get("/", response_model=list[schemas.OrderOut])
def list_orders(status: str = "", customer_id: int = 0, db: Session = Depends(get_db)):
    q = db.query(models.Order)
    if status:
        q = q.filter(models.Order.status == status)
    if customer_id:
        q = q.filter(models.Order.customer_id == customer_id)
    return q.order_by(models.Order.created_at.desc()).all()

@router.get("/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    return order

@router.patch("/{order_id}/status", response_model=schemas.OrderOut)
def update_status(order_id: int, data: schemas.StatusUpdate, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")
    order.status = data.status
    db.commit()
    db.refresh(order)
    return order
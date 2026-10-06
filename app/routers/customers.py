from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.post("/", response_model=schemas.CustomerOut)
def create_customer(data: schemas.CustomerCreate, db: Session = Depends(get_db)):
    if db.query(models.Customer).filter_by(phone=data.phone).first():
        raise HTTPException(400, "A customer with this phone number already exists")
    customer = models.Customer(**data.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer

@router.get("/", response_model=list[schemas.CustomerOut])
def list_customers(search: str = "", db: Session = Depends(get_db)):
    q = db.query(models.Customer)
    if search:
        q = q.filter(
            models.Customer.name.ilike(f"%{search}%")
            | models.Customer.phone.contains(search)
        )
    return q.order_by(models.Customer.name).all()

@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    return customer

@router.delete("/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(models.Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    if customer.orders:
        raise HTTPException(400, "Cannot delete a customer who has orders")
    db.delete(customer)
    db.commit()
    return {"deleted": customer_id}
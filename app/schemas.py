from datetime import datetime, date
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

ServiceType = Literal["wash", "iron", "wash_iron", "dry_clean"]
OrderStatus = Literal["received", "processing", "ready", "delivered"]


class CustomerCreate(BaseModel):
    name: str
    phone: str
    address: Optional[str] = None

class CustomerOut(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class OrderItemCreate(BaseModel):
    garment: str
    service: ServiceType
    quantity: int = Field(default=1, gt=0)
    unit_price: int = Field(gt=0)          # naira
    notes: Optional[str] = None

class OrderItemOut(OrderItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int

class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_number: str
    total: int
    amount_paid: int
    balance: int
    payment_status: str
    created_at: datetime

class OrderCreate(BaseModel):
    customer_id: int
    due_date: Optional[datetime] = None
    items: list[OrderItemCreate] = Field(min_length=1)

class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: int
    status: str
    due_date: Optional[datetime]
    created_at: datetime
    items: list[OrderItemOut]
    invoice: Optional[InvoiceOut]

class StatusUpdate(BaseModel):
    status: OrderStatus

PaymentMethod = Literal["cash", "transfer", "pos"]

class PaymentCreate(BaseModel):
    invoice_number: str
    amount: int = Field(gt=0)
    method: PaymentMethod
    reference: Optional[str] = None

class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    amount: int
    method: str
    reference: Optional[str]
    paid_at: datetime

class InvoiceDetail(BaseModel):
    invoice_number: str
    date: datetime
    customer_name: str
    customer_phone: str
    status: str
    due_date: Optional[datetime]
    items: list[OrderItemOut]
    total: int
    amount_paid: int
    balance: int
    payment_status: str
    payments: list[PaymentOut]

class ExpenseCreate(BaseModel):
    category: str
    description: Optional[str] = None
    amount: int = Field(gt=0)
    expense_date: Optional[date] = None

class ExpenseOut(ExpenseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    expense_date: date
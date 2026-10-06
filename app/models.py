from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base
from .utils import today_wat

class Customer(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    address = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    orders = relationship("Order", back_populates="customer")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    status = Column(String, default="received")  # received, processing, ready, delivered
    due_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    invoice = relationship("Invoice", back_populates="order", uselist=False)

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    garment = Column(String, nullable=False)      # e.g. "Shirt", "Duvet", "Agbada"
    service = Column(String, nullable=False)      # wash, iron, wash_iron, dry_clean
    quantity = Column(Integer, default=1)
    unit_price = Column(Integer, nullable=False)  # naira
    notes = Column(String)                        # e.g. "stain on collar"
    order = relationship("Order", back_populates="items")

class Invoice(Base):
    __tablename__ = "invoices"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    invoice_number = Column(String, unique=True, nullable=False)
    total = Column(Integer, nullable=False)       # naira
    created_at = Column(DateTime, default=datetime.utcnow)
    order = relationship("Order", back_populates="invoice")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")

    @property
    def amount_paid(self) -> int:
        return sum(p.amount for p in self.payments)

    @property
    def balance(self) -> int:
        return self.total - self.amount_paid

    @property
    def payment_status(self) -> str:
        paid = self.amount_paid
        if paid == 0:
            return "unpaid"
        return "paid" if paid >= self.total else "part_paid"

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount = Column(Integer, nullable=False)          # naira
    method = Column(String, nullable=False)           # cash, transfer, pos
    reference = Column(String)                        # transfer reference, optional
    paid_at = Column(DateTime, default=datetime.utcnow)
    invoice = relationship("Invoice", back_populates="payments")

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True)
    category = Column(String, nullable=False)         # detergent, electricity, salary...
    description = Column(String)
    amount = Column(Integer, nullable=False)          # naira
    expense_date = Column(Date, default=today_wat)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
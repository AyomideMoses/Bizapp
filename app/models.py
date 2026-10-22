from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, ForeignKey, Text
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
    total = Column(Integer, nullable=False)       # naira, this order's items only
    created_at = Column(DateTime, default=datetime.utcnow)
    order = relationship("Order", back_populates="invoice")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    carry_ins = relationship("CarryForward", foreign_keys="CarryForward.to_invoice_id",
                             back_populates="to_invoice", cascade="all, delete-orphan")
    carry_outs = relationship("CarryForward", foreign_keys="CarryForward.from_invoice_id",
                              back_populates="from_invoice")

    @property
    def amount_paid(self) -> int:
        return sum(p.amount for p in self.payments)

    @property
    def carried_in(self) -> int:       # old debt added to this invoice
        return sum(c.amount for c in self.carry_ins)

    @property
    def carried_out(self) -> int:      # this invoice's debt moved onto a later invoice
        return sum(c.amount for c in self.carry_outs)

    @property
    def amount_due(self) -> int:       # items plus brought-forward debt
        return self.total + self.carried_in

    @property
    def payable(self) -> int:          # what this invoice itself still has to collect in total
        return self.amount_due - self.carried_out

    @property
    def balance(self) -> int:
        return self.payable - self.amount_paid

    @property
    def payment_status(self) -> str:
        if self.balance <= 0:
            return "carried_forward" if self.carried_out > 0 else "paid"
        return "part_paid" if self.amount_paid > 0 else "unpaid"
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
    category = Column(String, nullable=False)
    description = Column(String)
    amount = Column(Integer, nullable=False)
    expense_date = Column(Date, default=today_wat)
    created_at = Column(DateTime, default=datetime.utcnow)
class User(Base):
     __tablename__ = "users"
     id = Column(Integer, primary_key=True)
     username = Column(String, unique=True, nullable=False)
     full_name = Column(String, nullable=False)
     password_hash = Column(String, nullable=False)
     role = Column(String, default="staff")        # admin or staff
     is_active = Column(Boolean, default=True)
     created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, index=True)      # plain numbers on purpose, so the log
    customer_id = Column(Integer, index=True)   # survives when orders or customers are deleted
    customer_name = Column(String)
    invoice_number = Column(String)
    kind = Column(String, nullable=False)       # received, ready, receipt, balance, delayed
    channel = Column(String, default="whatsapp_link")
    phone = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    sent_by = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class CarryForward(Base):
    __tablename__ = "carry_forwards"
    id = Column(Integer, primary_key=True)
    from_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    to_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    from_invoice = relationship("Invoice", foreign_keys=[from_invoice_id], back_populates="carry_outs")
    to_invoice = relationship("Invoice", foreign_keys=[to_invoice_id], back_populates="carry_ins")
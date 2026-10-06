from fastapi import FastAPI
from .database import Base, engine
from . import models
from .routers import customers, orders, invoices, payments, expenses, dashboard


Base.metadata.create_all(bind=engine)
app = FastAPI(title="BizApp")
app.include_router(customers.router)
app.include_router(orders.router)
app.include_router(invoices.router)
app.include_router(payments.router)
app.include_router(expenses.router)
app.include_router(dashboard.router)

@app.get("/")
def home():
    return {"status": "running"}
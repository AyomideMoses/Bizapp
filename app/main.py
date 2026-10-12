from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from .database import Base, engine, SessionLocal
from . import models
import os
from .security import hash_password
from .security import get_current_user, require_admin
from .routers import (
    customers, orders, invoices, payments, expenses,
    dashboard, auth, users, backups, web, web_orders, web_admin, web_messages
)

Base.metadata.create_all(bind=engine)
def bootstrap_admin():
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip().lower()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    full_name = os.getenv("BOOTSTRAP_ADMIN_NAME", "").strip()

    # Do nothing unless all three variables are configured.
    if not username or not password or not full_name:
        return

    db = SessionLocal()
    try:
        existing = db.query(models.User).filter_by(
            username=username
        ).first()

        if existing:
            return

        admin = models.User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()


bootstrap_admin()
app = FastAPI(title="BizApp")

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

@app.exception_handler(web.LoginRedirect)
async def send_to_login(request, exc):
    return RedirectResponse("/login", status_code=303)

# Web pages (each page checks the login itself)
app.include_router(web.router)
app.include_router(web_orders.router)
app.include_router(web_admin.router)
app.include_router(web_messages.router)
# Open to anyone: API login only
app.include_router(auth.router)

# Any logged-in staff member
for r in (customers, orders, invoices, payments):
    app.include_router(r.router, dependencies=[Depends(get_current_user)])

# Admins only
for r in (expenses, dashboard, users, backups):
    app.include_router(r.router, dependencies=[Depends(require_admin)])

@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/app")
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..security import hash_password, verify_password
from .web import templates, web_user
from .web_admin import password_error

router = APIRouter(include_in_schema=False)

def page(request, user, error=None, message=None, status=200):
    return templates.TemplateResponse(
        request, "account.html",
        {"user": user, "page": "account", "error": error, "message": message},
        status_code=status,
    )

@router.get("/app/account")
def account(request: Request, user=Depends(web_user)):
    return page(request, user)

@router.post("/app/account/password")
def change_password(request: Request, old_password: str = Form(""),
                    new_password: str = Form(""), confirm: str = Form(""),
                    user=Depends(web_user), db: Session = Depends(get_db)):
    if not verify_password(old_password, user.password_hash):
        return page(request, user, "Your current password is incorrect.", status=400)
    if new_password != confirm:
        return page(request, user, "The new passwords don't match.", status=400)
    error = password_error(new_password)
    if error:
        return page(request, user, error, status=400)
    if verify_password(new_password, user.password_hash):
        return page(request, user, "Choose a password different from your current one.", status=400)
    user.password_hash = hash_password(new_password)
    db.commit()
    return page(request, user, message="Password changed.")

@router.get("/app/more")
def more(request: Request, user=Depends(web_user)):
    return templates.TemplateResponse(request, "more.html", {"user": user, "page": "more"})
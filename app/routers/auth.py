from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..security import verify_password, hash_password, create_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter_by(username=form.username.strip().lower()).first()
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    return {"access_token": create_token(user.id), "token_type": "bearer"}

@router.get("/me", response_model=schemas.UserOut)
def me(user=Depends(get_current_user)):
    return user

@router.post("/change-password")
def change_password(data: schemas.PasswordChange, user=Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "Old password is incorrect")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"detail": "Password changed"}
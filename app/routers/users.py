from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..security import hash_password, require_admin

router = APIRouter(prefix="/users", tags=["Users"])

@router.post("/", response_model=schemas.UserOut)
def create_user(data: schemas.UserCreate, db: Session = Depends(get_db)):
    username = data.username.strip().lower()
    if db.query(models.User).filter_by(username=username).first():
        raise HTTPException(400, "Username already taken")
    user = models.User(
        username=username,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.get("/", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.username).all()

@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, data: schemas.UserUpdate, db: Session = Depends(get_db),
                admin=Depends(require_admin)):
    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "You cannot change your own role or active status")
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    db.commit()
    db.refresh(user)
    return user
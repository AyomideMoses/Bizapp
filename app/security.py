from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from . import config, models
from .database import get_db

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False

def create_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": expires}, config.SECRET_KEY, algorithm="HS256")

def user_from_token(token, db: Session):
    """Return the active user for a token, or None if it is missing or invalid."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
        user = db.get(models.User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    if not user or not user.is_active:
        return None
    return user

def get_current_user(request: Request, bearer: str = Depends(oauth2), db: Session = Depends(get_db)):
    user = user_from_token(bearer or request.cookies.get("token"), db)
    if not user:
        raise HTTPException(401, "Invalid or expired login", headers={"WWW-Authenticate": "Bearer"})
    return user

def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Admins only")
    return user
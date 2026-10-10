import getpass
from app.database import Base, engine, SessionLocal
from app import models
from app.security import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

username = input("Admin usergit add .name: ").strip().lower()
if db.query(models.User).filter_by(username=username).first():
    raise SystemExit("That username already exists.")

full_name = input("Full name: ").strip()
password = getpass.getpass("Password (8-64 characters): ")
if not 8 <= len(password) <= 64:
    raise SystemExit("Password must be 8-64 characters.")

db.add(models.User(username=username, full_name=full_name,
                   password_hash=hash_password(password), role="admin"))
db.commit()
print(f"Admin '{username}' created.")
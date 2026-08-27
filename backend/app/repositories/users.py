from sqlalchemy import select
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).first()


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_reset_hash(db: Session, token_hash: str) -> User | None:
    user = db.scalars(select(User).where(User.password_reset_token == token_hash)).first()
    if user is None or user.password_reset_expires is None:
        return None
    expires = user.password_reset_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        return None
    return user


def create_user(db: Session, *, name: str, email: str, password_hash: str) -> User:
    user = User(name=name, email=email, password=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_reset_token(db: Session, user: User, *, token_hash: str, expires) -> None:
    user.password_reset_token = token_hash
    user.password_reset_expires = expires
    db.commit()


def set_password(db: Session, user: User, password_hash: str) -> User:
    user.password = password_hash
    user.password_reset_token = None
    user.password_reset_expires = None
    db.commit()
    db.refresh(user)
    return user


def update_name(db: Session, user: User, name: str) -> User:
    user.name = name
    db.commit()
    db.refresh(user)
    return user

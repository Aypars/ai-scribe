from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.scalars(select(User).where(User.email == email)).first()


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create_user(db: Session, *, name: str, email: str, password_hash: str) -> User:
    user = User(name=name, email=email, password=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

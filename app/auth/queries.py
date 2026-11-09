from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User


def user_named(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))

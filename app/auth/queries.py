from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User


def user_named(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


@dataclass(frozen=True)
class RegisterView:
    invite_code: str


def register_view(invite_code: str) -> RegisterView:
    return RegisterView(invite_code=invite_code)

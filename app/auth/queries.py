from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.core.config import settings


def user_named(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def invite_required() -> bool:
    return bool(settings.invite_code)


@dataclass(frozen=True)
class RegisterView:
    invite_required: bool


def register_view() -> RegisterView:
    return RegisterView(invite_required=invite_required())

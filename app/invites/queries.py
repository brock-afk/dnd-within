from datetime import datetime

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.orm import Session

from app.invites.models import Invite
from app.invites.rules import code_hash


def is_active(now: datetime) -> ColumnElement[bool]:
    return and_(Invite.used_at.is_(None), Invite.revoked_at.is_(None), Invite.expires_at > now)


def with_code(code: str) -> ColumnElement[bool]:
    return Invite.code_hash == code_hash(code)


def active_invite(db: Session, code: str) -> Invite | None:
    return db.scalar(select(Invite).where(with_code(code), is_active(datetime.now())))

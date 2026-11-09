import secrets
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.models import User
from app.invites.form import InviteForm
from app.invites.models import Invite
from app.invites.queries import is_active, with_code
from app.invites.rules import INVITE_LIFETIME, code_hash


def create_invite(db: Session, note: str) -> tuple[Invite, str]:
    code = secrets.token_urlsafe(16)
    invite = Invite(
        code_hash=code_hash(code), note=note, expires_at=datetime.now() + INVITE_LIFETIME
    )
    db.add(invite)
    db.flush()
    return invite, code


def create_from_form(db: Session, form: InviteForm) -> tuple[Invite, str] | str:
    if problem := form.problem():
        return problem
    return create_invite(db, form.note)


def revoke(db: Session, invite: Invite) -> str | None:
    now = datetime.now()
    result = db.execute(
        update(Invite).where(Invite.id == invite.id, is_active(now)).values(revoked_at=now)
    )
    if result.rowcount != 1:
        return "Only an active invite can be revoked."
    return None


def claim(db: Session, code: str, user: User) -> bool:
    now = datetime.now()
    result = db.execute(
        update(Invite)
        .where(with_code(code), is_active(now))
        .values(used_at=now, used_by_id=user.id)
    )
    return result.rowcount == 1

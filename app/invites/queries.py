from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.orm import Session, joinedload

from app.auth.models import User
from app.invites.models import Invite
from app.invites.rules import InviteStatus, code_hash, status


def is_active(now: datetime) -> ColumnElement[bool]:
    return and_(Invite.used_at.is_(None), Invite.revoked_at.is_(None), Invite.expires_at > now)


def with_code(code: str) -> ColumnElement[bool]:
    return Invite.code_hash == code_hash(code)


def active_invite(db: Session, code: str) -> Invite | None:
    return db.scalar(select(Invite).where(with_code(code), is_active(datetime.now())))


def all_invites(db: Session) -> list[Invite]:
    query = select(Invite).options(joinedload(Invite.used_by)).order_by(Invite.id.desc())
    return list(db.scalars(query))


def _day(moment: datetime, now: datetime) -> str:
    day = f"{moment:%b} {moment.day}"
    return day if moment.year == now.year else f"{day}, {moment.year}"


def _detail(invite: Invite, invite_status: InviteStatus, now: datetime) -> str:
    match invite_status:
        case InviteStatus.ACTIVE:
            return f"expires {_day(invite.expires_at, now)}"
        case InviteStatus.USED:
            who = invite.used_by.username if invite.used_by else "a deleted account"
            return f"used by {who} on {_day(invite.used_at, now)}"
        case InviteStatus.EXPIRED:
            return f"expired {_day(invite.expires_at, now)}"
        case InviteStatus.REVOKED:
            return f"revoked {_day(invite.revoked_at, now)}"


@dataclass(frozen=True)
class InviteEntry:
    id: int
    note: str
    status: InviteStatus
    detail: str
    created: str
    revocable: bool


@dataclass(frozen=True)
class CreatedInvite:
    note: str
    code: str
    expires: str


@dataclass(frozen=True)
class InvitesView:
    user: User
    invites: list[InviteEntry]
    created: CreatedInvite | None
    note: str


def _entry(invite: Invite, now: datetime) -> InviteEntry:
    invite_status = status(invite, now)
    return InviteEntry(
        id=invite.id,
        note=invite.note,
        status=invite_status,
        detail=_detail(invite, invite_status, now),
        created=_day(invite.created_at, now),
        revocable=invite_status is InviteStatus.ACTIVE,
    )


def invites_view(
    db: Session, admin: User, created: tuple[Invite, str] | None = None, note: str = ""
) -> InvitesView:
    now = datetime.now()
    new = None
    if created:
        invite, code = created
        new = CreatedInvite(note=invite.note, code=code, expires=_day(invite.expires_at, now))
    return InvitesView(
        user=admin, invites=[_entry(i, now) for i in all_invites(db)], created=new, note=note
    )

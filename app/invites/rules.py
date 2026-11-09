import hashlib
from datetime import datetime, timedelta

from app.core.enums import LabeledEnum
from app.invites.models import Invite

INVITE_LIFETIME = timedelta(days=7)


class InviteStatus(LabeledEnum):
    ACTIVE = "active"
    USED = "used"
    EXPIRED = "expired"
    REVOKED = "revoked"


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def status(invite: Invite, now: datetime) -> InviteStatus:
    if invite.used_at is not None:
        return InviteStatus.USED
    if invite.revoked_at is not None:
        return InviteStatus.REVOKED
    if invite.expires_at <= now:
        return InviteStatus.EXPIRED
    return InviteStatus.ACTIVE

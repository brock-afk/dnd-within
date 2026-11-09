from datetime import datetime

from sqlalchemy import select

from app.invites.models import Invite
from app.invites.rules import InviteStatus, code_hash, status
from app.invites.service import claim, create_invite, revoke


def test_an_invite_stores_only_the_hash_of_its_code(db):
    invite, code = create_invite(db, "Alex")
    stored = db.execute(select(Invite.__table__).where(Invite.id == invite.id)).one()
    assert code not in stored
    assert invite.code_hash == code_hash(code)


def test_an_invite_is_claimed_once(db, invite, owner, other_user):
    _, code = invite
    assert claim(db, code, owner)
    assert not claim(db, code, other_user)


def test_only_an_active_invite_can_be_revoked(db, invite, owner):
    row, code = invite
    assert revoke(db, row) is None
    db.refresh(row)
    assert status(row, datetime.now()) is InviteStatus.REVOKED
    assert not claim(db, code, owner)
    assert revoke(db, row) == "Only an active invite can be revoked."

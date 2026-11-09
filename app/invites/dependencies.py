from typing import Annotated

from fastapi import Depends, HTTPException

from app.core.db import DbSession
from app.invites.models import Invite


def get_invite(invite_id: int, db: DbSession) -> Invite:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status_code=404)
    return invite


InviteRow = Annotated[Invite, Depends(get_invite)]

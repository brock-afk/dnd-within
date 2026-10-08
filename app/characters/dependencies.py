from typing import Annotated

from fastapi import Depends, HTTPException

from app.auth.dependencies import CurrentUser
from app.characters.models import Character
from app.core.db import DbSession


def get_owned_character(character_id: int, db: DbSession, user: CurrentUser) -> Character:
    character = db.get(Character, character_id)
    # Same response for "doesn't exist" and "not yours", so ids can't be probed.
    if character is None or character.user_id != user.id:
        raise HTTPException(status_code=404)
    return character


OwnedCharacter = Annotated[Character, Depends(get_owned_character)]

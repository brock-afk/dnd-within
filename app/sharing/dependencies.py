from typing import Annotated

from fastapi import Depends, HTTPException

from app.characters.models import Character
from app.core.db import DbSession
from app.sharing.queries import shared_character


def get_shared_character(token: str, db: DbSession) -> Character:
    character = shared_character(db, token)
    if character is None:
        raise HTTPException(status_code=404)
    return character


SharedCharacter = Annotated[Character, Depends(get_shared_character)]

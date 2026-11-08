from typing import Annotated

from fastapi import Depends, HTTPException

from app.auth.dependencies import CurrentUser
from app.characters.models import Character
from app.core.db import DbSession


def get_owned_character(character_id: int, db: DbSession, user: CurrentUser) -> Character:
    character = db.get(Character, character_id)
    if character is None or character.user_id != user.id:
        raise HTTPException(status_code=404)
    return character


OwnedCharacter = Annotated[Character, Depends(get_owned_character)]


def owned_child[T](db: DbSession, model: type[T], row_id: int, character: Character) -> T:
    row = db.get(model, row_id)
    if row is None or row.character_id != character.id:
        raise HTTPException(status_code=404)
    return row

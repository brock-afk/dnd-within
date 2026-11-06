from typing import Annotated

from fastapi import Depends, HTTPException

from app.characters.dependencies import OwnedCharacter
from app.core.db import DbSession
from app.features.models import Choice
from app.features.service import applicable_choice


def get_increase_choice(choice_id: int, db: DbSession, character: OwnedCharacter) -> Choice:
    """An ability score increase choice the character has."""
    choice = applicable_choice(db, character, choice_id)
    if choice is None or choice.kind != "ability_scores":
        raise HTTPException(status_code=404)
    return choice


IncreaseChoice = Annotated[Choice, Depends(get_increase_choice)]

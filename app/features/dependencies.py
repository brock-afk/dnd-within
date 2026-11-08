from typing import Annotated

from fastapi import Depends, HTTPException

from app.characters.dependencies import OwnedCharacter
from app.core.db import DbSession
from app.features.kinds import KINDS
from app.features.models import Choice
from app.features.queries import applicable_choice


def get_applicable_choice(choice_id: int, db: DbSession, character: OwnedCharacter) -> Choice:
    choice = applicable_choice(db, character, choice_id)
    if choice is None or choice.retired_at or choice.feature.retired_at:
        raise HTTPException(status_code=404)
    return choice


ApplicableChoice = Annotated[Choice, Depends(get_applicable_choice)]


def get_grid_choice(choice: ApplicableChoice) -> Choice:
    if KINDS[choice.kind].editor != "choices" or choice.in_play:
        raise HTTPException(status_code=404)
    return choice


GridChoice = Annotated[Choice, Depends(get_grid_choice)]


def get_in_play_choice(choice: ApplicableChoice) -> Choice:
    if not choice.in_play:
        raise HTTPException(status_code=404)
    return choice


InPlayChoice = Annotated[Choice, Depends(get_in_play_choice)]

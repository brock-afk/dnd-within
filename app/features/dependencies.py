from typing import Annotated

from fastapi import Depends, HTTPException

from app.characters.dependencies import OwnedCharacter
from app.core.db import DbSession
from app.features.kinds import KINDS
from app.features.models import Choice
from app.features.queries import applicable_choice


def get_applicable_choice(choice_id: int, db: DbSession, character: OwnedCharacter) -> Choice:
    """A choice the character has: its feature applies at their level."""
    choice = applicable_choice(db, character, choice_id)
    # Not in applicable_choice: remove_inapplicable_picks uses it, and picks made before a
    # choice was retired are kept. Retired ones just can't be opened or changed.
    if choice is None or choice.retired_at or choice.feature.retired_at:
        raise HTTPException(status_code=404)
    return choice


ApplicableChoice = Annotated[Choice, Depends(get_applicable_choice)]


def get_grid_choice(choice: ApplicableChoice) -> Choice:
    """A choice made on the Build page's option grid. Kinds with their own editor (ability
    score increases) and choices made on the Play sheet have one way in each."""
    if KINDS[choice.kind].editor != "choices" or choice.in_play:
        raise HTTPException(status_code=404)
    return choice


GridChoice = Annotated[Choice, Depends(get_grid_choice)]


def get_in_play_choice(choice: ApplicableChoice) -> Choice:
    if not choice.in_play:
        raise HTTPException(status_code=404)
    return choice


InPlayChoice = Annotated[Choice, Depends(get_in_play_choice)]

from typing import Annotated

from fastapi import Depends, HTTPException

from app.features.dependencies import ApplicableChoice
from app.features.models import Choice


def get_increase_choice(choice: ApplicableChoice) -> Choice:
    if choice.kind != "ability_scores":
        raise HTTPException(status_code=404)
    return choice


IncreaseChoice = Annotated[Choice, Depends(get_increase_choice)]

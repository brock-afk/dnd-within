"""Saving ability scores and ability score increases. Each operation returns its errors with
nothing changed, or none once it's done. They flush, never commit."""

from sqlalchemy.orm import Session

from app.abilities.form import AbilityForm, IncreaseForm
from app.abilities.rules import validate
from app.characters.models import Character
from app.features.kinds import KINDS
from app.features.models import Choice
from app.features.service import remove_inapplicable_picks
from app.sheet.service import tracking_max_hp


def save_scores(db: Session, character: Character, form: AbilityForm) -> dict[str, str]:
    """{field: problem}, keyed like rules.validate, or {} once saved. A Constitution change
    moves max HP: an increase raises current HP too, a decrease caps it."""
    scores = form.scores()
    if errors := validate(form.method, scores, form.roll_values()):
        return errors
    with tracking_max_hp(db, character, heal=True):
        character.ability_method = form.method
        for column, score in scores.items():
            setattr(character, column, score)
    return {}


def save_increase(
    db: Session, character: Character, choice: Choice, form: IncreaseForm
) -> str | None:
    """Save the +2/+1 (or +1 each) split. A Constitution increase raises max HP, and current
    HP with it."""
    kind = KINDS["ability_scores"]
    split = kind.split(choice, form.plus2, form.plus1, form.split == "even")
    if split is None:
        return "Choose where the +2 and the +1 go."
    with tracking_max_hp(db, character, heal=True):
        kind.save(db, choice, character.id, [kind.key(split)])
        remove_inapplicable_picks(db, character)
    return None

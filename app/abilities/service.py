from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abilities.models import CharacterAbilityBonus
from app.abilities.rules import ABILITIES, MAX_SCORE, modifier
from app.characters.models import Character


@dataclass(frozen=True)
class AbilityView:
    abbr: str
    name: str
    base: int
    bonus: int

    @property
    def total(self) -> int:
        return min(self.base + self.bonus, MAX_SCORE)

    @property
    def mod(self) -> int:
        return modifier(self.total)

    @property
    def modifier(self) -> str:
        return f"+{self.mod}" if self.mod >= 0 else f"−{-self.mod}"


def bonus_totals(
    db: Session, character: Character, except_choice_id: int | None = None
) -> dict[str, int]:
    """{ability: total bonus} from every choice, or every choice but one (to show scores
    before that choice's increases)."""
    query = select(CharacterAbilityBonus).where(CharacterAbilityBonus.character_id == character.id)
    if except_choice_id is not None:
        query = query.where(CharacterAbilityBonus.choice_id != except_choice_id)
    bonuses: dict[str, int] = defaultdict(int)
    for row in db.scalars(query):
        bonuses[row.ability] += row.amount
    return bonuses


def ability_views(
    db: Session, character: Character, except_choice_id: int | None = None
) -> list[AbilityView] | None:
    """Final scores for display, or None if the character hasn't set them yet. With
    `except_choice_id`, leaves out that choice's bonuses."""
    if character.ability_method is None:
        return None
    bonuses = bonus_totals(db, character, except_choice_id)
    return [
        AbilityView(a.abbr, a.name, getattr(character, a.column), bonuses[a.abbr])
        for a in ABILITIES
    ]

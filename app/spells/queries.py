from sqlalchemy import select
from sqlalchemy.orm import Session

from app.spells.models import CharacterSpell


def character_spells(db: Session, character_id: int) -> list[CharacterSpell]:
    rows = db.scalars(select(CharacterSpell).where(CharacterSpell.character_id == character_id))
    return sorted(rows, key=lambda cs: (cs.spell.level, cs.spell.name))

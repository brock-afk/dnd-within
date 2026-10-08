from sqlalchemy import select
from sqlalchemy.orm import Session

from app.spells.models import CharacterSpell, SpellbookEntry


def character_spells(db: Session, character_id: int) -> list[CharacterSpell]:
    rows = db.scalars(select(CharacterSpell).where(CharacterSpell.character_id == character_id))
    return sorted(rows, key=lambda cs: (cs.spell.level, cs.spell.name))


def spellbook(db: Session, character_id: int) -> list[SpellbookEntry]:
    """The character's spellbook, ordered by spell level then name."""
    rows = db.scalars(select(SpellbookEntry).where(SpellbookEntry.character_id == character_id))
    return sorted(rows, key=lambda entry: (entry.spell.level, entry.spell.name))

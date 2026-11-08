from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.content.queries import available, visible
from app.spells.models import CharacterSpell, Spell, SpellbookEntry


def pickable_spells(user_id: int) -> Select[tuple[Spell]]:
    return select(Spell).where(available(Spell), visible(Spell, user_id))


def character_spells(db: Session, character_id: int) -> list[CharacterSpell]:
    rows = db.scalars(select(CharacterSpell).where(CharacterSpell.character_id == character_id))
    return sorted(rows, key=lambda cs: (cs.spell.level, cs.spell.name))


def spellbook(db: Session, character_id: int) -> list[SpellbookEntry]:
    rows = db.scalars(select(SpellbookEntry).where(SpellbookEntry.character_id == character_id))
    return sorted(rows, key=lambda entry: (entry.spell.level, entry.spell.name))

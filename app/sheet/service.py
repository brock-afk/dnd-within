from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.leveling.service import hit_points
from app.sheet.models import CharacterHpEffect, CharacterPlayState, CharacterPreparedSpell
from app.sheet.rules import apply_max_change, current_hp
from app.spells.models import Spell
from app.spells.queries import character_spells, spellbook


@dataclass
class HpView:
    base: int  # from level history and Constitution
    effects: list[CharacterHpEffect]
    current: int
    temp: int
    temp_source: str | None

    @property
    def maximum(self) -> int:
        return max(0, self.base + sum(e.max_hp_delta for e in self.effects))


def play_state(db: Session, character: Character) -> CharacterPlayState:
    """The character's play state, created (at full HP) the first time it's needed."""
    state = db.get(CharacterPlayState, character.id)
    if state is None:
        state = CharacterPlayState(character_id=character.id, temp_hp=0)
        db.add(state)
    return state


def hp_effects(db: Session, character: Character) -> list[CharacterHpEffect]:
    query = (
        select(CharacterHpEffect)
        .where(CharacterHpEffect.character_id == character.id)
        .order_by(CharacterHpEffect.created_at, CharacterHpEffect.id)
    )
    return list(db.scalars(query))


def max_hp(db: Session, character: Character) -> int | None:
    """Base max HP plus active effects, or None until ability scores are set."""
    base = hit_points(db, character)
    if base is None:
        return None
    return max(0, base.maximum + sum(e.max_hp_delta for e in hp_effects(db, character)))


def hp_view(db: Session, character: Character) -> HpView | None:
    base = hit_points(db, character)
    if base is None:
        return None
    effects = hp_effects(db, character)
    state = db.get(CharacterPlayState, character.id)
    view = HpView(
        base.maximum,
        effects,
        current=0,
        temp=state.temp_hp if state else 0,
        temp_source=state.temp_hp_source if state else None,
    )
    view.current = current_hp(state, view.maximum)
    return view


def track_max_change(db: Session, character: Character, old_max: int | None, heal: bool) -> None:
    """Apply app/sheet/rules.py:apply_max_change after something changed max HP.

    Callers read max_hp() before making their change and pass it in; this reads the new value.
    Does nothing if there was no max HP before (ability scores weren't set). Doesn't commit.
    """
    db.flush()
    new_max = max_hp(db, character)
    if old_max is None or new_max is None or old_max == new_max:
        return
    apply_max_change(play_state(db, character), old_max, new_max, heal)


# --- Spells -------------------------------------------------------------------------------


def _spellcasting(character: Character) -> tuple[int, dict] | None:
    """(class level, spellcasting rules) of the character's spellcasting class.

    Only one spellcasting class until multiclassing; None if they have none.
    """
    for cc in character.classes:
        if cc.character_class.spellcasting and cc.level >= 1:
            return cc.level, cc.character_class.spellcasting
    return None


def prepared_limit(character: Character) -> int | None:
    """How many spells the character can prepare, from their spellcasting class's table."""
    found = _spellcasting(character)
    return found[1]["prepared"][found[0] - 1] if found else None


@dataclass(frozen=True)
class CastableSpell:
    spell: Spell
    ritual_only: bool = False  # in the spellbook but not prepared: castable only as a ritual


def castable_spells(db: Session, character: Character) -> list[CastableSpell]:
    """Everything the character can cast right now, by level then name: cantrips, prepared
    spells, and, for a Wizard (Ritual Adept), any other ritual in the spellbook as a ritual."""
    prepared = prepared_spell_ids(db, character)
    found = _spellcasting(character)
    rituals_from_book = bool(found) and found[1].get("ritual_casting") == "spellbook"

    rows = [
        CastableSpell(cs.spell) for cs in character_spells(db, character.id) if cs.spell.level == 0
    ]
    for entry in spellbook(db, character.id):
        if entry.spell_id in prepared:
            rows.append(CastableSpell(entry.spell))
        elif rituals_from_book and entry.spell.ritual:
            rows.append(CastableSpell(entry.spell, ritual_only=True))
    return sorted(rows, key=lambda r: (r.spell.level, r.spell.name))


def prepared_spell_ids(db: Session, character: Character) -> set[int]:
    query = select(CharacterPreparedSpell.spell_id).where(
        CharacterPreparedSpell.character_id == character.id
    )
    return set(db.scalars(query))


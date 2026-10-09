from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.leveling.service import hit_points
from app.sheet.models import (
    CharacterHpEffect,
    CharacterPlayState,
    CharacterPreparedSpell,
    CharacterSpellSlot,
)
from app.sheet.rules import apply_max_change, current_hp
from app.sheet.slots import slot_maximums
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


RITUALS_GROUP = "Rituals · no slot, +10 minutes"


@dataclass(frozen=True)
class CastableSpell:
    spell: Spell
    prepared: bool = False
    # Listed under Rituals: cast as a ritual (10 minutes longer, no slot), never with a slot.
    in_ritual_section: bool = False

    @property
    def group(self) -> str:
        if self.in_ritual_section:
            return RITUALS_GROUP
        return "Cantrips" if self.spell.level == 0 else f"Level {self.spell.level}"

    @property
    def uses_slots(self) -> bool:
        return not self.in_ritual_section and self.spell.level > 0

    @property
    def order(self) -> tuple:
        """Cantrips, then Rituals, then Level 1-9; by name within each."""
        if self.in_ritual_section:
            section = 1
        else:
            section = 0 if self.spell.level == 0 else 1 + self.spell.level
        return (section, self.spell.level, self.spell.name)


def castable_spells(db: Session, character: Character) -> list[CastableSpell]:
    """Everything the character can cast right now: cantrips; every spell castable as a
    ritual (prepared rituals, plus for a Wizard's Ritual Adept the other rituals in the
    spellbook); and prepared spells by level, cast with slots. A prepared ritual is listed
    twice, since it can be cast either way."""
    prepared = prepared_spell_ids(db, character)
    found = _spellcasting(character)
    rituals_from_book = bool(found) and found[1].get("ritual_casting") == "spellbook"

    rows = [
        CastableSpell(cs.spell) for cs in character_spells(db, character.id) if cs.spell.level == 0
    ]
    for entry in spellbook(db, character.id):
        is_prepared = entry.spell_id in prepared
        if is_prepared:
            rows.append(CastableSpell(entry.spell, prepared=True))
        if entry.spell.ritual and (is_prepared or rituals_from_book):
            rows.append(CastableSpell(entry.spell, prepared=is_prepared, in_ritual_section=True))
    return sorted(rows, key=lambda r: r.order)


# --- Spell slots --------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotLevel:
    level: int
    maximum: int
    expended: int

    @property
    def remaining(self) -> int:
        return self.maximum - min(self.expended, self.maximum)


def spell_slots(db: Session, character: Character) -> dict[int, SlotLevel]:
    """{slot level: SlotLevel} for the character's spellcasting class; empty if none."""
    found = _spellcasting(character)
    if not found:
        return {}
    class_level, spellcasting = found
    maximums = slot_maximums(spellcasting.get("slots", "full"), class_level)
    used = {
        row.slot_level: row.expended
        for row in db.scalars(
            select(CharacterSpellSlot).where(CharacterSpellSlot.character_id == character.id)
        )
    }
    return {lvl: SlotLevel(lvl, mx, used.get(lvl, 0)) for lvl, mx in maximums.items()}


def set_slots_remaining(db: Session, character: Character, level: int, remaining: int) -> None:
    """Record that `remaining` slots of this level are left (the caller validated it)."""
    maximum = spell_slots(db, character)[level].maximum
    row = db.get(CharacterSpellSlot, (character.id, level))
    if row is None:
        row = CharacterSpellSlot(character_id=character.id, slot_level=level, expended=0)
        db.add(row)
    row.expended = maximum - remaining


def prepared_spell_ids(db: Session, character: Character) -> set[int]:
    query = select(CharacterPreparedSpell.spell_id).where(
        CharacterPreparedSpell.character_id == character.id
    )
    return set(db.scalars(query))


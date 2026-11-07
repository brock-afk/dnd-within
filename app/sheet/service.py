from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.sheet.models import (
    CharacterAcEffect,
    CharacterPlayState,
    CharacterSpellSlot,
)
from app.sheet.queries import max_hp, spell_slots
from app.sheet.rules import apply_max_change
from app.spells.models import Spell


def play_state(db: Session, character: Character) -> CharacterPlayState:
    """The character's play state, created (at full HP) the first time it's needed."""
    state = db.get(CharacterPlayState, character.id)
    if state is None:
        state = CharacterPlayState(
            character_id=character.id, temp_hp=0, cp=0, sp=0, ep=0, gp=0, pp=0
        )
        db.add(state)
    return state


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


@contextmanager
def tracking_max_hp(db: Session, character: Character, heal: bool) -> Iterator[None]:
    """Make a change that may move max HP inside this block; current HP then follows it
    (track_max_change), without the caller having to read the old max first."""
    old_max = max_hp(db, character)
    yield
    track_max_change(db, character, old_max, heal)


def _ends_on_long_rest(spell: Spell) -> bool:
    """Spells lasting 8 hours or less are over by the end of a long rest."""
    duration = spell.details.get("duration", {})
    if duration.get("kind") != "timed":
        return False
    return duration["unit"] in ("round", "minute") or (
        duration["unit"] == "hour" and duration["amount"] <= 8
    )


def apply_ac_spell(db: Session, character: Character, spell: Spell) -> None:
    """Add the spell's AC effect, replacing one from an earlier casting (recasting refreshes,
    never stacks). The caller spends the slot."""
    db.execute(
        delete(CharacterAcEffect).where(
            CharacterAcEffect.character_id == character.id,
            CharacterAcEffect.spell_id == spell.id,
        )
    )
    effect = spell.details["ac_effect"]
    db.add(
        CharacterAcEffect(
            character_id=character.id,
            label=spell.name,
            kind=effect["kind"],
            value=effect["value"],
            spell_id=spell.id,
            ends_on_long_rest=_ends_on_long_rest(spell),
        )
    )


def set_slots_remaining(db: Session, character: Character, level: int, remaining: int) -> None:
    """Record that `remaining` slots of this level are left (the caller validated it)."""
    slot = spell_slots(db, character)[level]
    row = db.get(CharacterSpellSlot, (character.id, slot.kind, level))
    if row is None:
        row = CharacterSpellSlot(
            character_id=character.id, kind=slot.kind, slot_level=level, expended=0
        )
        db.add(row)
    row.expended = slot.maximum - remaining

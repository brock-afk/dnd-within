from collections.abc import Iterator
from contextlib import contextmanager
from typing import NamedTuple

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.core.forms import parse_amount
from app.sheet import rules
from app.sheet.form import AcEffectForm
from app.sheet.models import (
    CharacterAcEffect,
    CharacterFeatureUse,
    CharacterHpEffect,
    CharacterPlayState,
    CharacterSpellSlot,
)
from app.sheet.queries import (
    FeatureUses,
    ability_modifier,
    ac_spells,
    castable_spells,
    damage_reactions,
    feature_uses,
    max_hp,
    spell_slots,
)
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


@contextmanager
def tracking_max_hp(db: Session, character: Character, heal: bool) -> Iterator[None]:
    """Current HP is stored, so a change to max HP must move it by the PHB rules in
    app/sheet/rules.py:apply_max_change."""
    old_max = max_hp(db, character)
    yield
    db.flush()
    new_max = max_hp(db, character)
    if old_max is None or new_max is None or old_max == new_max:
        return  # None until ability scores are set
    rules.apply_max_change(play_state(db, character), old_max, new_max, heal)


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


def set_uses_remaining(
    db: Session, character: Character, uses: FeatureUses, remaining: int
) -> None:
    row = db.get(CharacterFeatureUse, (character.id, uses.feature.id))
    if row is None:
        row = CharacterFeatureUse(character_id=character.id, feature_id=uses.feature.id, expended=0)
        db.add(row)
    row.expended = uses.maximum - remaining


def spend_slot(db: Session, character: Character, spell_key: str, slot_level: str) -> str | None:
    """Spend the slot for casting a prepared spell at `slot_level` (its level or higher)."""
    # A prepared ritual is listed twice (as a ritual and at its level); casting uses the slot row.
    row = next(
        (
            r
            for r in castable_spells(db, character)
            if str(r.spell.id) == spell_key and r.uses_slots
        ),
        None,
    )
    slots = spell_slots(db, character)
    level = parse_amount(slot_level, 1, 9)
    if row is None:
        return "Only prepared spells of level 1 or higher are cast with a slot."
    if level is None or level < row.spell.level:
        return f"{row.spell.name} needs a slot of level {row.spell.level} or higher."
    if level not in slots or slots[level].remaining == 0:
        return f"You have no level {level} slots left."
    set_slots_remaining(db, character, level, slots[level].remaining - 1)
    return None


# --- Hit points and Armor Class -----------------------------------------------------------


class HpOutcome(NamedTuple):
    errors: dict[str, str]
    pending_damage: int | None


def change_hp(
    db: Session, character: Character, action: str, amount: str, skip_reactions: str
) -> HpOutcome:
    maximum = max_hp(db, character)
    value = parse_amount(amount, 0, 999)
    if maximum is None or action not in ("damage", "heal") or value is None:
        return HpOutcome({"hp": "Enter a whole number from 0 to 999."}, None)
    offer_reactions = action == "damage" and value and not skip_reactions
    if offer_reactions and damage_reactions(feature_uses(db, character)):
        # Offer reactions like Stone's Endurance before the damage lands.
        return HpOutcome({}, value)
    (rules.take_damage if action == "damage" else rules.heal)(
        play_state(db, character), value, maximum
    )
    return HpOutcome({}, None)


def react_to_damage(
    db: Session, character: Character, amount: str, option_id: str, roll: str
) -> HpOutcome:
    """Use a damage reaction (Stone's Endurance, Storm's Thunder...), then take the damage."""
    maximum = max_hp(db, character)
    value = parse_amount(amount, 1, 999)
    reactions = damage_reactions(feature_uses(db, character))
    reaction = next((r for r in reactions if str(r.option.id) == option_id), None)
    if maximum is None or value is None or reaction is None:
        return HpOutcome({"hp": "That reaction isn't available right now."}, None)

    if reaction.kind == "reduce":
        low, high = reaction.die_count, reaction.die_count * reaction.die_sides
        rolled = parse_amount(roll, low, high)
        if rolled is None:
            return HpOutcome(
                {"reaction": f"Enter your {reaction.dice} roll, from {low} to {high}."}, value
            )
        ability = reaction.option.damage_reaction.get("ability")
        reduction = rolled + (ability_modifier(db, character, ability) if ability else 0)
        value = max(0, value - reduction)

    set_uses_remaining(db, character, reaction.uses, reaction.uses.remaining - 1)
    rules.take_damage(play_state(db, character), value, maximum)
    return HpOutcome({}, None)


def change_temp_hp(db: Session, character: Character, amount: str, source: str) -> str | None:
    value = parse_amount(amount, 0, 999)
    if value is None:
        return "Enter a whole number from 0 to 999."
    rules.set_temp_hp(play_state(db, character), value, source.strip()[:80])
    return None


def add_hp_effect(db: Session, character: Character, label: str, delta: str) -> str | None:
    value = parse_amount(delta, -999, 999)
    label = label.strip()[:80]
    if not label or not value:
        return "Give the effect a name and a non-zero amount (e.g. Aid, +5)."
    # Starting an effect like Aid heals by the increase; a drain only caps current HP.
    with tracking_max_hp(db, character, heal=value > 0):
        db.add(CharacterHpEffect(character_id=character.id, label=label, max_hp_delta=value))
    return None


def end_hp_effect(db: Session, character: Character, effect: CharacterHpEffect) -> None:
    # Ending an effect never heals: Aid ending only caps current HP, and a drain wearing off
    # raises max HP without restoring any.
    with tracking_max_hp(db, character, heal=False):
        db.delete(effect)


def cast_ac_spell(db: Session, character: Character, spell: str, slot_level: str) -> str | None:
    """Cast an AC spell on yourself (Mage Armor, Barkskin): spend the slot, or with
    `slot_level` "at_will" cast it free through a feature like Armor of Shadows, and apply its
    effect. Casting from the spell list doesn't, since the target may be someone else."""
    ac = next((a for a in ac_spells(db, character) if str(a.spell.id) == spell), None)
    if ac is None:
        return "Only spells that change your AC can be cast here."
    if slot_level == "at_will":
        if not ac.at_will_from:
            return f"{ac.spell.name} isn't cast at will."
    elif error := spend_slot(db, character, spell, slot_level):
        return error
    apply_ac_spell(db, character, ac.spell)
    return None


def add_ac_effect(db: Session, character: Character, form: AcEffectForm) -> str | None:
    label = form.label[:80]
    amount = form.amount()
    if not label or not amount:
        return f"Give the effect a name and {form.hint}."
    db.add(
        CharacterAcEffect(
            character_id=character.id, label=label, kind=form.effect_kind, value=amount
        )
    )
    return None


def end_ac_effect(db: Session, effect: CharacterAcEffect) -> None:
    db.delete(effect)

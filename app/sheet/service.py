from collections.abc import Iterator
from contextlib import contextmanager
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.abilities.queries import constitution_modifier
from app.characters.models import Character
from app.core.forms import parse_amount, parse_id
from app.features.kinds import KINDS
from app.features.models import Choice, Feature
from app.features.queries import always_prepared_error
from app.sheet import rules
from app.sheet.form import AcEffectForm, RecoveryForm
from app.sheet.models import (
    CharacterAcEffect,
    CharacterFeatureUse,
    CharacterHitDice,
    CharacterHpEffect,
    CharacterPlayState,
    CharacterPreparedSpell,
    CharacterSpellSlot,
)
from app.sheet.queries import (
    FeatureUses,
    Spender,
    ability_modifier,
    ac_spells,
    castable_spells,
    copyable,
    damage_reactions,
    feature_uses,
    granted_spells,
    hit_dice,
    max_hp,
    prepared_limit,
    recovery_budget,
    spell_slots,
    uses_of,
)
from app.spells.models import Spell, SpellbookEntry
from app.spells.queries import spellbook
from app.spells.rules import AcquiredVia, DurationKind, DurationUnit, SlotKind


def play_state(db: Session, character: Character) -> CharacterPlayState:
    state = db.get(CharacterPlayState, character.id)
    if state is None:
        state = CharacterPlayState(
            character_id=character.id, temp_hp=0, cp=0, sp=0, ep=0, gp=0, pp=0
        )
        db.add(state)
    return state


@contextmanager
def tracking_max_hp(db: Session, character: Character, heal: bool) -> Iterator[None]:
    old_max = max_hp(db, character)
    yield
    db.flush()
    new_max = max_hp(db, character)
    if old_max is None or new_max is None or old_max == new_max:
        return
    rules.apply_max_change(play_state(db, character), old_max, new_max, heal)


def _ends_on_long_rest(spell: Spell) -> bool:
    duration = spell.details.get("duration", {})
    if duration.get("kind") != DurationKind.TIMED:
        return False
    return duration["unit"] in (DurationUnit.ROUND, DurationUnit.MINUTE) or (
        duration["unit"] == DurationUnit.HOUR and duration["amount"] <= 8
    )


def apply_ac_spell(db: Session, character: Character, spell: Spell) -> None:
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
        return HpOutcome({}, value)
    (rules.take_damage if action == "damage" else rules.heal)(
        play_state(db, character), value, maximum
    )
    return HpOutcome({}, None)


def react_to_damage(
    db: Session, character: Character, amount: str, option_id: str, roll: str
) -> HpOutcome:
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
    with tracking_max_hp(db, character, heal=value > 0):
        db.add(CharacterHpEffect(character_id=character.id, label=label, max_hp_delta=value))
    return None


def end_hp_effect(db: Session, character: Character, effect: CharacterHpEffect) -> None:
    with tracking_max_hp(db, character, heal=False):
        db.delete(effect)


def cast_ac_spell(db: Session, character: Character, spell: str, slot_level: str) -> str | None:
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


def spend_slot(db: Session, character: Character, spell_key: str, slot_level: str) -> str | None:
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


def save_prepared(db: Session, character: Character, picks: list[str]) -> str | None:
    picks = list(dict.fromkeys(picks))
    book = {str(entry.spell_id): entry.spell_id for entry in spellbook(db, character.id)}
    limit = prepared_limit(character)
    if limit is None:
        return "This character doesn't prepare spells."
    if any(key not in book for key in picks):
        return "You can only prepare spells in your spellbook."
    if refused := always_prepared_error(db, character, picks):
        return refused
    if len(picks) > limit:
        return f"You can prepare at most {limit}. You picked {len(picks)}."
    db.execute(
        delete(CharacterPreparedSpell).where(CharacterPreparedSpell.character_id == character.id)
    )
    db.add_all(
        CharacterPreparedSpell(character_id=character.id, spell_id=book[key]) for key in picks
    )
    db.flush()
    return None


def remove_copied_spell(db: Session, character: Character, key: str) -> str | None:
    entry = next((e for e in spellbook(db, character.id) if str(e.spell_id) == key), None)
    if entry is None or entry.acquired_via != AcquiredVia.COPIED:
        return "Only copied spells can be removed here. Change level-up spells on the Build page."
    db.delete(entry)
    db.flush()
    return None


def change_slots(db: Session, character: Character, level: int, remaining: str) -> str | None:
    slot = spell_slots(db, character).get(level)
    value = parse_amount(remaining, 0, slot.maximum) if slot else None
    if value is None:
        return "That isn't a valid number of slots."
    set_slots_remaining(db, character, level, value)
    return None


def cast_free(db: Session, character: Character, spell: str, feature: str) -> str | None:
    granted = granted_spells(db, character).get(parse_id(spell))
    uses = uses_of(db, character, parse_id(feature))
    if granted is None or uses is None:
        return "That spell can't be cast for free."
    feature_spell, granting = granted
    if not feature_spell.free_cast or uses.feature != granting:
        return "That spell can't be cast for free."
    cost = feature_spell.charge_cost
    if uses.remaining < cost:
        if uses.remaining:
            return f"{uses.feature.name}: {uses.remaining} left, and this takes {cost}."
        return f"{uses.feature.name}'s free cast is used. It comes back on a long rest."
    set_uses_remaining(db, character, uses, uses.remaining - cost)
    return None


def copy_spell(db: Session, character: Character, spell: str, note: str) -> str | None:
    found = copyable(db, spell, character.user_id)
    if found is None:
        return "Choose a spell of level 1 or higher to copy."
    if found.id in {entry.spell_id for entry in spellbook(db, character.id)}:
        return f"{found.name} is already in your spellbook."
    if refused := always_prepared_error(db, character, [str(found.id)]):
        return refused
    db.add(
        SpellbookEntry(
            character_id=character.id,
            spell_id=found.id,
            acquired_via=AcquiredVia.COPIED,
            source_note=note.strip()[:120] or None,
        )
    )
    return None


def set_play_choice(db: Session, character: Character, choice: Choice, pick: str) -> str | None:
    kind = KINDS[choice.kind]
    if not pick:
        kind.clear(db, [choice.id], character.id)
        return None
    return kind.save(db, choice, character.id, [pick])


def change_uses(db: Session, character: Character, uses: FeatureUses, remaining: str) -> str | None:
    value = parse_amount(remaining, 0, uses.maximum)
    if value is None:
        return "That isn't a valid number of uses."
    set_uses_remaining(db, character, uses, value)
    return None


def use_spender(db: Session, character: Character, spender: Spender) -> str | None:
    uses, feature = spender.uses, spender.feature
    if uses.remaining < feature.spends_amount:
        return f"{feature.name} takes {feature.spends_amount}; {uses.remaining} left."
    set_uses_remaining(db, character, uses, uses.remaining - feature.spends_amount)
    return None


def spend_hit_die(db: Session, character: Character, class_id: str, roll: str) -> str | None:
    dice = next((d for d in hit_dice(db, character) if str(d.character_class.id) == class_id), None)
    maximum = max_hp(db, character)
    con_mod = constitution_modifier(db, character)
    if dice is None or maximum is None or con_mod is None:
        return "Set ability scores first: hit dice heal using Constitution."
    if dice.available == 0:
        return "You have no hit dice left. They come back on a long rest."
    rolled = parse_amount(roll, 1, dice.die)
    if rolled is None:
        return f"Enter your d{dice.die} roll, from 1 to {dice.die}."

    row = db.get(CharacterHitDice, (character.id, dice.character_class.id))
    if row is None:
        row = CharacterHitDice(character_id=character.id, class_id=dice.character_class.id, spent=0)
        db.add(row)
    row.spent += 1
    rules.heal(play_state(db, character), rules.hit_die_healing(rolled, con_mod), maximum)
    return None


def recover_slots(
    db: Session, character: Character, uses: FeatureUses, form: RecoveryForm
) -> str | None:
    name = uses.feature.name
    if uses.remaining == 0:
        return f"{name} is used. It comes back on a long rest."
    slots = spell_slots(db, character)
    counts = form.counts(slots)
    if counts is None:
        return "Enter how many slots of each level to recover."
    max_level = uses.feature.slot_recovery["max_slot_level"]
    for level, count in counts.items():
        spent = slots[level].maximum - slots[level].remaining
        if level > max_level:
            return f"{name} can't recover slots above level {max_level}."
        if count > spent:
            return f"You only have {spent} level {level} slots spent."
    if not counts:
        return "Choose at least one slot to recover."
    budget = recovery_budget(uses)
    if sum(level * n for level, n in counts.items()) > budget:
        return f"{name} recovers at most {budget} total slot levels."

    for level, n in counts.items():
        set_slots_remaining(db, character, level, slots[level].remaining + n)
    set_uses_remaining(db, character, uses, uses.remaining - 1)
    return None


def finish_short_rest(db: Session, character: Character) -> None:
    db.execute(
        delete(CharacterSpellSlot).where(
            CharacterSpellSlot.character_id == character.id,
            CharacterSpellSlot.kind == SlotKind.PACT,
        )
    )
    for uses in feature_uses(db, character):
        if uses.recharge == "short_rest":
            db.execute(
                delete(CharacterFeatureUse).where(
                    CharacterFeatureUse.character_id == character.id,
                    CharacterFeatureUse.feature_id == uses.feature.id,
                )
            )


def long_rest(db: Session, character: Character) -> None:
    db.execute(delete(CharacterHpEffect).where(CharacterHpEffect.character_id == character.id))
    state = play_state(db, character)
    state.current_hp = None
    state.temp_hp = 0
    state.temp_hp_source = None
    for row, feature in db.execute(
        select(CharacterFeatureUse, Feature)
        .join(Feature, Feature.id == CharacterFeatureUse.feature_id)
        .where(CharacterFeatureUse.character_id == character.id)
    ):
        regain = (feature.uses or {}).get("regain")
        if regain:
            regained = max(0, rules.roll(regain))
            maximum = rules.uses_maximum(feature.uses["max"], character.level)
            row.expended = max(0, min(row.expended, maximum) - regained)
        else:
            db.delete(row)
    for model in (CharacterHitDice, CharacterSpellSlot):
        db.execute(delete(model).where(model.character_id == character.id))
    db.execute(
        delete(CharacterAcEffect).where(
            CharacterAcEffect.character_id == character.id,
            CharacterAcEffect.ends_on_long_rest.is_(True),
        )
    )

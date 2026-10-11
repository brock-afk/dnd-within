"""Limited-use features, hit dice, and short and long rests (2024 rules).

Generic: any feature whose content declares `uses` gets tracked, and any feature declaring
`slot_recovery` can be used during a short rest. Nothing here knows about a specific class.
"""

import math
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.classes.models import CharacterClass
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature
from app.features.service import feature_groups
from app.sheet.models import (
    CharacterAcEffect,
    CharacterFeatureUse,
    CharacterHitDice,
    CharacterHpEffect,
    CharacterSpellSlot,
)
from app.sheet.rules import proficiency_bonus, roll
from app.sheet.service import play_state

# --- Limited-use features -----------------------------------------------------------------


@dataclass(frozen=True)
class FeatureUses:
    feature: Feature
    maximum: int
    expended: int
    class_level: int  # the owning class's level (character level for species features)
    # The options the character picked for this feature's choices (e.g. Stone's Endurance for
    # Giant Ancestry), which say what a use actually does and when.
    options: tuple[ChoiceOption, ...] = ()
    # Features that spend these uses when used, like a magic item's Stonecunning (its charges).
    spenders: tuple[Feature, ...] = ()

    @property
    def remaining(self) -> int:
        return self.maximum - min(self.expended, self.maximum)

    @property
    def recharge(self) -> str:
        return self.feature.uses["recharge"]

    @property
    def rest_only(self) -> bool:
        """Used only during a rest (like Arcane Recovery), so it lives in the rest panel."""
        return self.feature.slot_recovery is not None


def _class_level(character: Character, feature: Feature) -> int:
    if feature.class_id is not None:
        return character.class_level(feature.class_id)
    if feature.subclass_id is not None:
        for cc in character.classes:
            if cc.subclass_id == feature.subclass_id:
                return cc.level
    return character.level


def _maximum(character: Character, feature: Feature) -> int:
    maximum = feature.uses["max"]
    return proficiency_bonus(character.level) if maximum == "proficiency_bonus" else maximum


def feature_uses(db: Session, character: Character) -> list[FeatureUses]:
    """Every limited-use feature the character has (respecting level, class, subclass and
    species, exactly like the character page)."""
    spent = {
        row.feature_id: row.expended
        for row in db.scalars(
            select(CharacterFeatureUse).where(CharacterFeatureUse.character_id == character.id)
        )
    }
    picked: dict[int, list[ChoiceOption]] = {}
    for option, feature_id in db.execute(
        select(ChoiceOption, Choice.feature_id)
        .join(CharacterChoicePick, CharacterChoicePick.option_id == ChoiceOption.id)
        .join(Choice, Choice.id == ChoiceOption.choice_id)
        .where(CharacterChoicePick.character_id == character.id)
        .order_by(ChoiceOption.position)
    ):
        picked.setdefault(feature_id, []).append(option)

    groups = feature_groups(db, character)
    spenders: dict[int, list[Feature]] = {}
    for group in groups:
        for fv in group.features:
            if fv.feature.spends_feature_id:
                spenders.setdefault(fv.feature.spends_feature_id, []).append(fv.feature)

    result = []
    for group in groups:
        for fv in group.features:
            feature = fv.feature
            if not feature.uses:
                continue
            level = _class_level(character, feature)
            options = tuple(picked.get(feature.id, ()))
            result.append(
                FeatureUses(
                    feature,
                    _maximum(character, feature),
                    spent.get(feature.id, 0),
                    level,
                    options,
                    tuple(spenders.get(feature.id, ())),
                )
            )
    return result


def set_uses_remaining(
    db: Session, character: Character, uses: FeatureUses, remaining: int
) -> None:
    row = db.get(CharacterFeatureUse, (character.id, uses.feature.id))
    if row is None:
        row = CharacterFeatureUse(character_id=character.id, feature_id=uses.feature.id, expended=0)
        db.add(row)
    row.expended = uses.maximum - remaining


# --- Hit dice -----------------------------------------------------------------------------


@dataclass(frozen=True)
class HitDice:
    character_class: CharacterClass
    total: int  # one per class level
    spent: int

    @property
    def available(self) -> int:
        return max(0, self.total - self.spent)

    @property
    def die(self) -> int:
        return self.character_class.hit_die


def hit_dice(db: Session, character: Character) -> list[HitDice]:
    spent = {
        row.class_id: row.spent
        for row in db.scalars(
            select(CharacterHitDice).where(CharacterHitDice.character_id == character.id)
        )
    }
    return [
        HitDice(cc.character_class, cc.level, spent.get(cc.class_id, 0)) for cc in character.classes
    ]


def spend_hit_die(db: Session, character: Character, class_id: int) -> None:
    row = db.get(CharacterHitDice, (character.id, class_id))
    if row is None:
        row = CharacterHitDice(character_id=character.id, class_id=class_id, spent=0)
        db.add(row)
    row.spent += 1


# --- Slot recovery (Arcane Recovery) ------------------------------------------------------


def recovery_budget(uses: FeatureUses) -> int:
    """Total slot levels the feature can recover: half the class level, rounded up."""
    return math.ceil(uses.class_level / 2)


# --- Rests --------------------------------------------------------------------------------


def finish_short_rest(db: Session, character: Character) -> None:
    """Restore every use that recharges on a short rest."""
    for uses in feature_uses(db, character):
        if uses.recharge == "short_rest":
            db.execute(
                delete(CharacterFeatureUse).where(
                    CharacterFeatureUse.character_id == character.id,
                    CharacterFeatureUse.feature_id == uses.feature.id,
                )
            )


def long_rest(db: Session, character: Character) -> None:
    """Full HP, no temporary HP, every hit die back (2024 rules), all spell slots and every
    feature use restored, and AC spells cast from the sheet ended. Every max HP effect ends: a
    reduced max returns to normal, and effects like Aid (8 hours) are over.

    Charges regained "at dawn" count as a long rest. Ones that regain a roll (1d3) get that
    many back instead of all."""
    db.execute(delete(CharacterHpEffect).where(CharacterHpEffect.character_id == character.id))
    state = play_state(db, character)
    state.current_hp = None  # at full, of the restored max
    state.temp_hp = 0
    state.temp_hp_source = None
    # Every spent-uses row, not just active features': an item regains its charges at dawn
    # whether or not it's attuned.
    for row, feature in db.execute(
        select(CharacterFeatureUse, Feature)
        .join(Feature, Feature.id == CharacterFeatureUse.feature_id)
        .where(CharacterFeatureUse.character_id == character.id)
    ):
        regain = (feature.uses or {}).get("regain")
        if regain:
            row.expended = max(0, min(row.expended, _maximum(character, feature)) - roll(regain))
        else:
            db.delete(row)
    for model in (CharacterHitDice, CharacterSpellSlot):
        db.execute(delete(model).where(model.character_id == character.id))
    # Spells like Mage Armor (8 hours) are over; AC effects added by hand stay.
    db.execute(
        delete(CharacterAcEffect).where(
            CharacterAcEffect.character_id == character.id,
            CharacterAcEffect.ends_on_long_rest.is_(True),
        )
    )


# --- Damage reactions ---------------------------------------------------------------------


@dataclass(frozen=True)
class DamageReaction:
    """A picked option the character can use in reaction to taking damage right now."""

    uses: FeatureUses
    option: ChoiceOption

    @property
    def kind(self) -> str:
        return self.option.damage_reaction["kind"]

    @property
    def dice(self) -> str:
        return self.option.damage_reaction["dice"]

    @property
    def die_count(self) -> int:
        return int(self.dice.split("d")[0])

    @property
    def die_sides(self) -> int:
        return int(self.dice.split("d")[1])


def damage_reactions(db: Session, character: Character) -> list[DamageReaction]:
    """Damage reactions with a use left, offered before damage is applied."""
    return [
        DamageReaction(uses, option)
        for uses in feature_uses(db, character)
        if uses.remaining > 0
        for option in uses.options
        if option.damage_reaction
    ]

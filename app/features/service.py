from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.abilities.models import CharacterAbilityBonus
from app.characters.models import Character
from app.classes.models import CharacterClassLevel, Subclass
from app.features.kinds import KINDS, OptionView
from app.features.models import Choice, Feature


@dataclass
class ChoiceView:
    choice: Choice
    picked: list[OptionView]

    @property
    def done(self) -> bool:
        return len(self.picked) >= self.choice.count


@dataclass
class FeatureView:
    feature: Feature
    choices: list[ChoiceView]


@dataclass
class FeatureGroup:
    """Features from one source: the species, or one of the character's classes."""

    name: str
    features: list[FeatureView]


def _applies(applies_to: str, cc: CharacterClassLevel) -> bool:
    if applies_to == "starting_class":
        return cc.is_starting_class
    if applies_to == "multiclass":
        return not cc.is_starting_class
    return True


def _views(db: Session, character: Character, features, level: int) -> list[FeatureView]:
    """Features with the choices unlocked at `level` (the class level, or the character level
    for species features)."""
    return [
        FeatureView(
            f,
            [
                ChoiceView(c, KINDS[c.kind].picked(db, c, character.id))
                for c in f.choices
                if c.level <= level
            ],
        )
        for f in features
    ]


def feature_groups(db: Session, character: Character) -> list[FeatureGroup]:
    """The species' features (by character level), then for each class its features and its
    subclass's features (both by that class's level)."""
    species_features = db.scalars(
        select(Feature)
        .where(Feature.species_id == character.species_id, Feature.level <= character.level)
        .order_by(Feature.position)
    ).all()
    groups = [
        FeatureGroup(
            character.species.name,
            _views(db, character, species_features, character.level),
        )
    ]

    for cc in character.classes:
        class_features = db.scalars(
            select(Feature)
            .where(Feature.class_id == cc.class_id, Feature.level <= cc.level)
            .order_by(Feature.position)
        ).all()
        applicable = [f for f in class_features if _applies(f.applies_to, cc)]
        groups.append(
            FeatureGroup(cc.character_class.name, _views(db, character, applicable, cc.level))
        )

        if cc.subclass_id is not None:
            subclass_features = db.scalars(
                select(Feature)
                .where(Feature.subclass_id == cc.subclass_id, Feature.level <= cc.level)
                .order_by(Feature.position)
            ).all()
            name = db.get(Subclass, cc.subclass_id).name
            groups.append(FeatureGroup(name, _views(db, character, subclass_features, cc.level)))
    return groups


def applicable_choice(db: Session, character: Character, choice_id: int) -> Choice | None:
    """The choice, if this character has its feature, using the same rules as feature_groups."""
    choice = db.get(Choice, choice_id)
    if choice is None:
        return None
    feature = choice.feature
    unlocks_at = max(feature.level, choice.level)
    if feature.species_id is not None:
        ok = feature.species_id == character.species_id and unlocks_at <= character.level
        return choice if ok else None
    for cc in character.classes:
        if feature.class_id is not None and cc.class_id == feature.class_id:
            ok = unlocks_at <= cc.level and _applies(feature.applies_to, cc)
            return choice if ok else None
        if feature.subclass_id is not None and cc.subclass_id == feature.subclass_id:
            return choice if unlocks_at <= cc.level else None
    return None


class _AbilityBonusPicks:
    """Ability bonuses aren't a choice kind of their own yet, but are cleaned up the same way."""

    def picked_choice_ids(self, db: Session, character_id: int) -> set[int]:
        query = select(CharacterAbilityBonus.choice_id).where(
            CharacterAbilityBonus.character_id == character_id
        )
        return set(db.scalars(query))

    def clear(self, db: Session, choice_ids: list[int], character_id: int) -> None:
        db.execute(
            delete(CharacterAbilityBonus).where(
                CharacterAbilityBonus.character_id == character_id,
                CharacterAbilityBonus.choice_id.in_(choice_ids),
            )
        )


def remove_inapplicable_picks(db: Session, character: Character) -> None:
    """Delete picks for choices the character no longer has, e.g. after losing a level or
    switching subclass.

    Repeats until nothing changes, because clearing one pick can make others stale: clearing
    a subclass removes its features, so their picks go too. Doesn't commit; the caller does,
    together with whatever made the picks stale.
    """
    pick_sources = [*KINDS.values(), _AbilityBonusPicks()]
    while True:
        changed = False
        for source in pick_sources:
            stale = [
                cid
                for cid in source.picked_choice_ids(db, character.id)
                if not applicable_choice(db, character, cid)
            ]
            if stale:
                source.clear(db, stale, character.id)
                changed = True
        if not changed:
            return
        db.flush()

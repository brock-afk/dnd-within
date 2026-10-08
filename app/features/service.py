from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.classes.models import CharacterClassLevel
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


def _views(db: Session, character: Character, features) -> list[FeatureView]:
    return [
        FeatureView(f, [ChoiceView(c, KINDS[c.kind].picked(db, c, character.id)) for c in f.choices])
        for f in features
    ]


def feature_groups(db: Session, character: Character) -> list[FeatureGroup]:
    """The species' features (by character level), then each class's (by that class's level)."""
    species_features = db.scalars(
        select(Feature)
        .where(Feature.species_id == character.species_id, Feature.level <= character.level)
        .order_by(Feature.position)
    ).all()
    groups = [FeatureGroup(character.species.name, _views(db, character, species_features))]

    for cc in character.classes:
        class_features = db.scalars(
            select(Feature)
            .where(Feature.class_id == cc.class_id, Feature.level <= cc.level)
            .order_by(Feature.position)
        ).all()
        applicable = [f for f in class_features if _applies(f.applies_to, cc)]
        groups.append(FeatureGroup(cc.character_class.name, _views(db, character, applicable)))
    return groups


def applicable_choice(db: Session, character: Character, choice_id: int) -> Choice | None:
    """The choice, if this character has its feature, using the same rules as feature_groups."""
    choice = db.get(Choice, choice_id)
    if choice is None:
        return None
    feature = choice.feature
    if feature.species_id is not None:
        ok = feature.species_id == character.species_id and feature.level <= character.level
        return choice if ok else None
    for cc in character.classes:
        if cc.class_id == feature.class_id:
            ok = feature.level <= cc.level and _applies(feature.applies_to, cc)
            return choice if ok else None
    return None

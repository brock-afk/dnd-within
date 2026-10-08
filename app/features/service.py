from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
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


def _feature_views(db: Session, character: Character, source_filter) -> list[FeatureView]:
    features = db.scalars(
        select(Feature)
        .where(source_filter, Feature.level <= character.level)
        .order_by(Feature.position)
    ).all()
    return [
        FeatureView(
            feature,
            [ChoiceView(c, KINDS[c.kind].picked(db, c, character.id)) for c in feature.choices],
        )
        for feature in features
    ]


def species_features(db: Session, character: Character) -> list[FeatureView]:
    return _feature_views(db, character, Feature.species_id == character.species_id)


def class_features(db: Session, character: Character) -> list[FeatureView]:
    return _feature_views(db, character, Feature.class_id == character.class_id)


def applicable_choice(db: Session, character: Character, choice_id: int) -> Choice | None:
    """The choice, if it belongs to this character's species or class at their level."""
    choice = db.get(Choice, choice_id)
    if choice is None:
        return None
    feature = choice.feature
    belongs = feature.species_id == character.species_id or feature.class_id == character.class_id
    return choice if belongs and feature.level <= character.level else None

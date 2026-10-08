from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.abilities.models import CharacterAbilityBonus
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


def remove_inapplicable_picks(db: Session, character: Character) -> None:
    """Delete picks for choices the character no longer has, e.g. after losing a level.

    Works across every choice kind and ability bonuses, so subclasses and multiclassing can
    reuse it. Doesn't commit; the caller does, together with whatever made picks stale.
    """
    pick_tables = [kind.pick for kind in KINDS.values()] + [CharacterAbilityBonus]
    picked = set()
    for table in pick_tables:
        query = select(table.choice_id).where(table.character_id == character.id)
        picked |= set(db.scalars(query))
    stale = [
        cid for cid in picked if cid is not None and not applicable_choice(db, character, cid)
    ]
    if not stale:
        return
    for table in pick_tables:
        db.execute(
            delete(table).where(table.character_id == character.id, table.choice_id.in_(stale))
        )

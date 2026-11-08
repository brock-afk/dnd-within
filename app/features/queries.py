from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.classes.models import CharacterClassLevel, Subclass
from app.content.queries import available
from app.features.kinds import (
    KINDS,
    OptionView,
    choice_count,
    current_count,
    owner_level,
    owner_level_name,
)
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature
from app.inventory.models import CharacterItem, Item
from app.spells.models import Spell
from app.spells.rules import School


@dataclass
class ChoiceView:
    choice: Choice
    picked: list[OptionView]
    level: int = 1
    level_name: str = "Level"
    count: int = 1
    url: str = ""

    @property
    def level_label(self) -> str:
        return f"{self.level_name} {self.level}" if self.level > 1 else ""

    @property
    def done(self) -> bool:
        return len(self.picked) >= self.count


@dataclass
class FeatureView:
    feature: Feature
    choices: list[ChoiceView]


@dataclass
class FeatureSection:
    title: str
    features: list[FeatureView]


@dataclass
class FeatureGroup:
    name: str
    kind: str
    sections: list[FeatureSection]
    change_url: str = ""

    @property
    def features(self) -> list[FeatureView]:
        return [fv for section in self.sections for fv in section.features]


def _applies(applies_to: str, cc: CharacterClassLevel) -> bool:
    if applies_to == "starting_class":
        return cc.is_starting_class
    if applies_to == "multiclass":
        return not cc.is_starting_class
    return True


def _views(
    db: Session, character: Character, features, level: int, level_name: str = "Level"
) -> list[FeatureView]:
    views = []
    for f in features:
        choices = [
            ChoiceView(
                c,
                KINDS[c.kind].picked(db, c, character.id),
                level=max(f.level, c.level),
                level_name=level_name,
                count=choice_count(c, level),
                url=f"/characters/{character.id}/{KINDS[c.kind].editor}/{c.id}",
            )
            for c in f.choices
            if c.level <= level and c.retired_at is None
        ]
        views.append(FeatureView(f, choices))
        picked = [int(o.key) for cv in choices if cv.choice.kind == "option" for o in cv.picked]
        if picked:
            option_features = db.scalars(
                select(Feature)
                .join(ChoiceOption, ChoiceOption.id == Feature.option_id)
                .where(Feature.option_id.in_(picked), Feature.level <= level, available(Feature))
                .order_by(ChoiceOption.position, Feature.position)
            ).all()
            views.extend(_views(db, character, option_features, level, level_name))
    return views


def _active_item_ids(db: Session, character: Character) -> list[int]:
    rows = db.scalars(select(CharacterItem).where(CharacterItem.character_id == character.id)).all()
    ids = {r.item_id for r in rows if r.attuned or not r.item.requires_attunement}
    return sorted(ids)


def _origin_feat_id(character: Character) -> int | None:
    return character.background.feat_id if character.background else None


def feature_groups(db: Session, character: Character) -> list[FeatureGroup]:

    def by_character_level(column, parent_id: int) -> list[FeatureView]:
        features = db.scalars(
            select(Feature)
            .where(column == parent_id, Feature.level <= character.level, available(Feature))
            .order_by(Feature.position)
        ).all()
        return _views(db, character, features, character.level)

    species = by_character_level(Feature.species_id, character.species_id)
    groups = [
        FeatureGroup(
            character.species.name,
            "Species",
            [FeatureSection("", species)],
            f"/characters/{character.id}/species",
        )
    ]
    if background := character.background:
        sections = [
            FeatureSection("", by_character_level(Feature.background_id, background.id)),
            FeatureSection(
                f"Origin feat · {background.feat.name}",
                by_character_level(Feature.feat_id, background.feat_id),
            ),
        ]
        groups.append(
            FeatureGroup(
                background.name, "Background", sections, f"/characters/{character.id}/background"
            )
        )

    for item_id in _active_item_ids(db, character):
        features = by_character_level(Feature.item_id, item_id)
        if features:
            item = db.get(Item, item_id)
            groups.append(
                FeatureGroup(item.name, item.category.label, [FeatureSection("", features)])
            )

    for cc in character.classes:
        class_features = db.scalars(
            select(Feature)
            .where(Feature.class_id == cc.class_id, Feature.level <= cc.level, available(Feature))
            .order_by(Feature.position)
        ).all()
        applicable = [f for f in class_features if _applies(f.applies_to, cc)]
        views = _views(db, character, applicable, cc.level, cc.character_class.name)
        groups.append(FeatureGroup(cc.character_class.name, "Class", [FeatureSection("", views)]))
        subclass_choice = next(
            (cv for fv in views for cv in fv.choices if cv.choice.kind == "subclass"), None
        )

        if cc.subclass_id is not None:
            subclass_features = db.scalars(
                select(Feature)
                .where(
                    Feature.subclass_id == cc.subclass_id,
                    Feature.level <= cc.level,
                    available(Feature),
                )
                .order_by(Feature.position)
            ).all()
            name = db.get(Subclass, cc.subclass_id).name
            views = _views(db, character, subclass_features, cc.level, cc.character_class.name)
            kind = f"{cc.character_class.name} subclass"
            url = subclass_choice.url if subclass_choice else ""
            groups.append(FeatureGroup(name, kind, [FeatureSection("", views)], url))
    return groups


def always_prepared_spells(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> dict[int, str]:
    found: dict[int, str] = {}
    for group in feature_groups(db, character) if groups is None else groups:
        for fv in group.features:
            for fs in fv.feature.spells:
                if fs.always_prepared and fs.spell.retired_at is None:
                    found.setdefault(fs.spell_id, fv.feature.name)
    return found


def always_prepared_reasons(db: Session, character: Character) -> dict[str, str]:
    return {
        str(spell_id): f"Always prepared ({feature})"
        for spell_id, feature in always_prepared_spells(db, character).items()
    }


def always_prepared_error(db: Session, character: Character, keys: list[str]) -> str | None:
    granted = {str(i): feature for i, feature in always_prepared_spells(db, character).items()}
    key = next((k for k in keys if k in granted), None)
    if key is None:
        return None
    return f"{db.get(Spell, int(key)).name} is always prepared ({granted[key]})."


@dataclass
class PlayChoice:
    feature: Feature
    choice: Choice
    options: list[OptionView]
    picked: OptionView | None


def play_choices(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> list[PlayChoice]:
    return [
        PlayChoice(
            fv.feature,
            cv.choice,
            KINDS[cv.choice.kind].options(db, cv.choice, character),
            cv.picked[0] if cv.picked else None,
        )
        for group in (feature_groups(db, character) if groups is None else groups)
        for fv in group.features
        for cv in fv.choices
        if cv.choice.in_play
    ]


def _level_label(db: Session, choice: Choice) -> str:
    level = max(choice.feature.level, choice.level)
    return f"{owner_level_name(db, choice.feature)} {level}" if level > 1 else ""


def applicable_choice(db: Session, character: Character, choice_id: int) -> Choice | None:
    choice = db.get(Choice, choice_id)
    if choice is None:
        return None
    feature = choice.feature
    unlocks_at = max(feature.level, choice.level)
    if feature.option_id is not None:
        option = db.get(ChoiceOption, feature.option_id)
        picked = db.scalar(
            select(CharacterChoicePick.id).where(
                CharacterChoicePick.character_id == character.id,
                CharacterChoicePick.option_id == option.id,
            )
        )
        ok = (
            picked is not None
            and applicable_choice(db, character, option.choice_id) is not None
            and unlocks_at <= owner_level(db, character, feature)
        )
        return choice if ok else None
    if feature.item_id is not None:
        ok = feature.item_id in _active_item_ids(db, character) and unlocks_at <= character.level
        return choice if ok else None
    for parent_id, character_has in [
        (feature.species_id, character.species_id),
        (feature.background_id, character.background_id),
        (feature.feat_id, _origin_feat_id(character)),
    ]:
        if parent_id is not None:
            ok = parent_id == character_has and unlocks_at <= character.level
            return choice if ok else None
    for cc in character.classes:
        if feature.class_id is not None and cc.class_id == feature.class_id:
            ok = unlocks_at <= cc.level and _applies(feature.applies_to, cc)
            return choice if ok else None
        if feature.subclass_id is not None and cc.subclass_id == feature.subclass_id:
            return choice if unlocks_at <= cc.level else None
    return None


@dataclass(frozen=True)
class ChoiceFormView:
    character: Character
    choice: Choice
    level_label: str
    count: int
    options: list[OptionView]
    filter_schools: list[School]
    known: dict[str, str]
    noun: tuple[str, str]
    selected: list[str]


def choice_form_view(
    db: Session, character: Character, choice: Choice, selected: list[str] | None = None
) -> ChoiceFormView:
    kind = KINDS[choice.kind]
    options = kind.options(db, choice, character)
    known = kind.unavailable(db, choice, character.id)
    if kind.blocks_always_prepared:
        known = always_prepared_reasons(db, character) | known
    if selected is None:
        selected = [o.key for o in kind.picked(db, choice, character.id)]
    return ChoiceFormView(
        character=character,
        choice=choice,
        level_label=_level_label(db, choice),
        count=current_count(db, character, choice),
        options=options,
        filter_schools=sorted({o.school for o in options if o.school}),
        known=known,
        noun=kind.noun,
        selected=selected,
    )

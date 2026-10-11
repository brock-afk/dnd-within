from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.classes.models import CharacterClass, CharacterClassLevel, Subclass
from app.content.queries import available
from app.features.kinds import KINDS, OptionView
from app.features.models import Choice, Feature
from app.inventory.models import CharacterItem, Item


@dataclass
class ChoiceView:
    choice: Choice
    picked: list[OptionView]
    level: int = 1  # the class level (character level for species, backgrounds, feats)
    level_name: str = "Level"  # "Wizard" for class and subclass choices, so "Wizard 2"

    @property
    def level_label(self) -> str:
        """ "Wizard 2", or "" for level 1 choices (no need to say)."""
        return f"{self.level_name} {self.level}" if self.level > 1 else ""

    @property
    def done(self) -> bool:
        return len(self.picked) >= self.choice.count


@dataclass
class FeatureView:
    feature: Feature
    choices: list[ChoiceView]


@dataclass
class FeatureSection:
    """Part of a group: its own features (no title), or features that come with it, like a
    background's origin feat ("Origin feat · Familiar Friend")."""

    title: str
    features: list[FeatureView]


@dataclass
class FeatureGroup:
    """Features from one source: the species, the background (with its origin feat), or one
    of the character's classes or subclasses."""

    name: str
    kind: str  # what the name is: "Species", "Background", "Class", "Wizard subclass"
    sections: list[FeatureSection]
    change_url: str = ""  # the form for picking a different one, shown by the group's name

    @property
    def features(self) -> list[FeatureView]:
        """Every feature in the group, across its sections."""
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
    """Features with the choices unlocked at `level` (the class level, or the character level
    for species features). `level_name` labels those levels, e.g. "Wizard"."""
    return [
        FeatureView(
            f,
            [
                ChoiceView(
                    c,
                    KINDS[c.kind].picked(db, c, character.id),
                    level=max(f.level, c.level),
                    level_name=level_name,
                )
                for c in f.choices
                if c.level <= level and c.retired_at is None
            ],
        )
        for f in features
    ]


def _active_item_ids(db: Session, character: Character) -> list[int]:
    """Items whose features apply: attuned ones, and carried ones that don't need attunement."""
    rows = db.scalars(select(CharacterItem).where(CharacterItem.character_id == character.id)).all()
    ids = {r.item_id for r in rows if r.attuned or not r.item.requires_attunement}
    return sorted(ids)


def _origin_feat_id(character: Character) -> int | None:
    """The origin feat the character's background gives, if they've picked one."""
    return character.background.feat_id if character.background else None


def feature_groups(db: Session, character: Character) -> list[FeatureGroup]:
    """The species', background's and origin feat's features (by character level), then those
    of magic items that are attuned (or carried, if they don't need it), then for each class
    its features and its subclass's features (both by that class's level). Features
    and choices retired from their pack aren't shown, though picks already made for them are
    kept."""

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
            groups.append(FeatureGroup(item.name, "Magic item", [FeatureSection("", features)]))

    for cc in character.classes:
        class_features = db.scalars(
            select(Feature)
            .where(Feature.class_id == cc.class_id, Feature.level <= cc.level, available(Feature))
            .order_by(Feature.position)
        ).all()
        applicable = [f for f in class_features if _applies(f.applies_to, cc)]
        views = _views(db, character, applicable, cc.level, cc.character_class.name)
        groups.append(FeatureGroup(cc.character_class.name, "Class", [FeatureSection("", views)]))
        # The subclass group is changed through this class's subclass choice.
        subclass_choice = next(
            (cv.choice for fv in views for cv in fv.choices if cv.choice.kind == "subclass"),
            None,
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
            url = (
                f"/characters/{character.id}/choices/{subclass_choice.id}"
                if subclass_choice
                else ""
            )
            groups.append(FeatureGroup(name, kind, [FeatureSection("", views)], url))
    return groups


@dataclass
class PlayChoice:
    """A choice made on the Play sheet (Choice.in_play), with every option it offers."""

    feature: Feature
    choice: Choice
    options: list[OptionView]
    picked: OptionView | None


def play_choices(db: Session, character: Character) -> list[PlayChoice]:
    """The character's in-play choices, following the same level, subclass and retired rules
    as feature_groups."""
    return [
        PlayChoice(
            fv.feature,
            cv.choice,
            KINDS[cv.choice.kind].options(db, cv.choice),
            cv.picked[0] if cv.picked else None,
        )
        for group in feature_groups(db, character)
        for fv in group.features
        for cv in fv.choices
        if cv.choice.in_play
    ]


def choice_level_label(db: Session, choice: Choice) -> str:
    """Like ChoiceView.level_label, for a choice on its own (e.g. its form)."""
    feature = choice.feature
    level = max(feature.level, choice.level)
    if level <= 1:
        return ""
    if feature.class_id is None and feature.subclass_id is None:
        return f"Level {level}"  # species, background and feat choices go by character level
    class_id = feature.class_id or db.get(Subclass, feature.subclass_id).class_id
    return f"{db.get(CharacterClass, class_id).name} {level}"


def applicable_choice(db: Session, character: Character, choice_id: int) -> Choice | None:
    """The choice, if this character has its feature, using the same rules as feature_groups."""
    choice = db.get(Choice, choice_id)
    if choice is None:
        return None
    feature = choice.feature
    unlocks_at = max(feature.level, choice.level)
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


def remove_inapplicable_picks(db: Session, character: Character) -> None:
    """Delete picks for choices the character no longer has, e.g. after losing a level or
    switching subclass, plus Expertise in skills they're no longer proficient in.

    Repeats until nothing changes, because clearing one pick can make others stale: clearing
    a subclass removes its features, so their picks go too. Doesn't commit; the caller does,
    together with whatever made the picks stale.
    """
    while True:
        changed = False
        for source in KINDS.values():
            stale = [
                cid
                for cid in source.picked_choice_ids(db, character.id)
                if not applicable_choice(db, character, cid)
            ]
            if stale:
                source.clear(db, stale, character.id)
                changed = True
        if not changed:
            break
        db.flush()
    # Expertise needs proficiency, which a changed skill pick may have just removed.
    KINDS["expertise"].remove_unproficient(db, character.id)


def fill_fixed_choices(db: Session, character: Character) -> None:
    """Pick choices that offer exactly as many options as they ask for, like a background's
    Animal Handling. A choice the save rejects (the character already has that skill from
    elsewhere) is left to pick by hand, as the rules say to choose another. Commits."""
    for group in feature_groups(db, character):
        for fv in group.features:
            for cv in fv.choices:
                if cv.picked or cv.choice.in_play:
                    continue
                kind = KINDS[cv.choice.kind]
                options = kind.options(db, cv.choice)
                if len(options) == cv.choice.count:
                    kind.save(db, cv.choice, character.id, [o.key for o in options])

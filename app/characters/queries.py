from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abilities.queries import AbilityView, ability_views
from app.auth.models import User
from app.characters.models import Character
from app.characters.origins import Origin
from app.classes.models import CharacterClass
from app.content.queries import available_by_name
from app.core.db import reload_all
from app.features.kinds import OptionView
from app.features.queries import ChoiceView, FeatureGroup, feature_groups
from app.leveling.queries import HitPoints, hit_points
from app.sheet.queries import spell_warnings
from app.skills.models import CharacterSkill
from app.skills.queries import character_skills, expertise_skill_ids
from app.species.models import Species
from app.spells.models import SpellbookEntry
from app.spells.queries import spellbook
from app.spells.rules import AcquiredVia


def pending_choices(groups: list[FeatureGroup]) -> list[ChoiceView]:
    return [
        cv
        for g in groups
        for fv in g.features
        for cv in fv.choices
        if not cv.done and not cv.choice.in_play
    ]


def needs_building(db: Session, character: Character) -> bool:
    if character.ability_method is None or character.background_id is None:
        return True
    return bool(pending_choices(feature_groups(db, character)))


@dataclass(frozen=True)
class CharacterListView:
    user: User
    characters: list[Character]
    links: dict[int, str]


def character_list_view(db: Session, user: User) -> CharacterListView:
    characters = list(
        db.scalars(
            select(Character)
            .where(Character.user_id == user.id)
            .order_by(Character.created_at.desc())
        )
    )
    links = {
        c.id: f"/characters/{c.id}" if needs_building(db, c) else f"/characters/{c.id}/sheet"
        for c in characters
    }
    return CharacterListView(user=user, characters=characters, links=links)


@dataclass(frozen=True)
class NewCharacterView:
    user: User
    classes: list[CharacterClass]
    species: list[Species]


def new_character_view(db: Session, user: User) -> NewCharacterView:
    return NewCharacterView(
        user=user,
        classes=available_by_name(db, CharacterClass),
        species=available_by_name(db, Species),
    )


@dataclass(frozen=True)
class BuildPageView:
    user: User | None
    character: Character
    read_only: bool
    base_url: str | None
    abilities: list[AbilityView] | None
    hit_points: HitPoints | None
    feature_groups: list[FeatureGroup]
    pending: list[ChoiceView]
    skills: list[CharacterSkill]
    expertise: set[int]
    copied_under: int | None
    copied: list[tuple[SpellbookEntry, list[str]]]


def build_page_view(
    db: Session,
    user: User | None,
    character: Character,
    *,
    read_only: bool = False,
    base_url: str | None = None,
) -> BuildPageView:
    groups = feature_groups(db, character)
    warnings = spell_warnings(db, character)
    return BuildPageView(
        user=user,
        character=character,
        read_only=read_only,
        base_url=base_url,
        abilities=ability_views(db, character),
        hit_points=hit_points(db, character),
        feature_groups=groups,
        pending=pending_choices(groups),
        skills=character_skills(db, character.id),
        expertise=expertise_skill_ids(db, character.id),
        copied_under=next(
            (
                fv.feature.id
                for g in groups
                for fv in g.features
                if any(cv.choice.kind == "spellbook" for cv in fv.choices)
            ),
            None,
        ),
        copied=[
            (entry, warnings.get(entry.spell_id, []))
            for entry in spellbook(db, character.id)
            if entry.acquired_via == AcquiredVia.COPIED
        ],
    )


def refreshed_build_view(db: Session, user: User, character: Character) -> BuildPageView:
    reload_all(db)
    return build_page_view(db, user, character)


@dataclass(frozen=True)
class OriginFormView:
    character: Character
    origin: Origin
    options: list[OptionView]
    selected: str


def origin_form_view(
    db: Session, character: Character, origin: Origin, selected: str | None = None
) -> OriginFormView:
    if selected is None:
        selected = str(getattr(character, origin.column) or "")
    return OriginFormView(
        character=character,
        origin=origin,
        options=[
            OptionView(str(row.id), row.name, row.summary, detail=origin.detail(row))
            for row in available_by_name(db, origin.model)
        ],
        selected=selected,
    )

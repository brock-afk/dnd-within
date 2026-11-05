"""View models for the character list, the new-character form and the Build page, loaded
from the database. Rendering them is app/characters/page.py's job."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abilities.service import AbilityView, ability_views
from app.auth.models import User
from app.characters.models import Character
from app.classes.models import CharacterClass
from app.content.queries import available_by_name
from app.features.service import ChoiceView, FeatureGroup, feature_groups
from app.leveling.service import HitPoints, hit_points
from app.sheet.service import spell_warnings
from app.skills.models import CharacterSkill
from app.skills.queries import character_skills, expertise_skill_ids
from app.species.models import Species
from app.spells.models import SpellbookEntry
from app.spells.queries import spellbook


def pending_choices(groups: list[FeatureGroup]) -> list[ChoiceView]:
    """Choices still to make on the Build page. In-play choices are optional and made on the
    Play sheet, so they're never pending."""
    return [
        cv
        for g in groups
        for fv in g.features
        for cv in fv.choices
        if not cv.done and not cv.choice.in_play
    ]


def needs_building(db: Session, character: Character) -> bool:
    """Whether the Build page has anything left to do: ability scores, a background, or a
    pending choice. Characters that don't open on the Play sheet."""
    if character.ability_method is None or character.background_id is None:
        return True
    return bool(pending_choices(feature_groups(db, character)))


@dataclass(frozen=True)
class CharacterListView:
    user: User
    characters: list[Character]
    links: dict[int, str]  # character id -> the page it opens on


def character_list_view(db: Session, user: User) -> CharacterListView:
    characters = list(
        db.scalars(
            select(Character)
            .where(Character.user_id == user.id)
            .order_by(Character.created_at.desc())
        )
    )
    # Open each on the Play sheet once it's built, on the Build page while it has choices left.
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
    """The Build page. `read_only` is the shared view: the same page with every control left
    out, its tabs linking within `base_url` (/shared/<token>)."""

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
    copied_under: int | None  # the feature whose section lists copied spells
    copied: list[tuple[SpellbookEntry, list[str]]]  # copied spells, with their rule markers


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
        # The first feature with spellbook choices (Spellcasting).
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
            if entry.acquired_via == "copied"
        ],
    )


def refreshed_build_view(db: Session, user: User, character: Character) -> BuildPageView:
    """The Build page after a change. Relationships loaded before it (a class row's subclass)
    would show stale, so everything is reloaded."""
    db.flush()  # expiring drops changes not yet sent to the database
    db.expire_all()
    return build_page_view(db, user, character)

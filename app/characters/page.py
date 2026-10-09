"""Rendering the character page, in full or as an in-place refresh.

Routes that change a character (choices, ability scores, levels) return
`refresh_character_page`, so htmx morphs the updated page into place: the scroll position
and focus stay where they were, instead of jumping to the top like a full page load.
"""

from fastapi import Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.abilities.service import ability_views
from app.auth.models import User
from app.characters.models import Character
from app.core.templates import morph_in_place, templates
from app.features.service import feature_groups
from app.leveling.service import hit_points
from app.sheet.service import spell_warnings
from app.skills.queries import character_skills
from app.spells.queries import spellbook

# The element in characters/show.html that a refresh replaces.
PAGE_SELECTOR = "#character-page"


def render_character_page(
    request: Request, db: Session, user: User, character: Character
) -> HTMLResponse:
    groups = feature_groups(db, character)
    pending = [cv for g in groups for fv in g.features for cv in fv.choices if not cv.done]
    warnings = spell_warnings(db, character)
    # Copied spells are listed under the first feature with spellbook choices (Spellcasting).
    copied_under = next(
        (
            fv.feature.id
            for g in groups
            for fv in g.features
            if any(cv.choice.kind == "spellbook" for cv in fv.choices)
        ),
        None,
    )
    return templates.TemplateResponse(
        request,
        "characters/show.html",
        {
            "user": user,
            "character": character,
            "abilities": ability_views(db, character),
            "hit_points": hit_points(db, character),
            "feature_groups": groups,
            "pending": pending,
            "skills": character_skills(db, character.id),
            "copied_under": copied_under,
            # Spells copied into the book (not from a level up), with their rule markers.
            "copied": [
                (entry, warnings.get(entry.spell_id, []))
                for entry in spellbook(db, character.id)
                if entry.acquired_via == "copied"
            ],
        },
    )


def refresh_character_page(
    request: Request, db: Session, user: User, character: Character
) -> HTMLResponse:
    """The full page, with headers telling htmx to morph just the page body into place,
    whatever element sent the request."""
    # Sessions don't expire objects on commit, so relationships loaded before the change
    # (e.g. a class row's subclass) would render stale. Reload everything from the database.
    db.expire_all()
    return morph_in_place(render_character_page(request, db, user, character), PAGE_SELECTOR)

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
from app.skills.queries import character_skills
from app.spells.queries import character_spells, spellbook

# The element in characters/show.html that a refresh replaces.
PAGE_SELECTOR = "#character-page"


def render_character_page(
    request: Request, db: Session, user: User, character: Character
) -> HTMLResponse:
    groups = feature_groups(db, character)
    pending = [cv for g in groups for fv in g.features for cv in fv.choices if not cv.done]
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
            "spells": character_spells(db, character.id),
            "spellbook": spellbook(db, character.id),
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

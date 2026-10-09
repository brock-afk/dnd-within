from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.characters.page import refresh_character_page
from app.core.db import DbSession
from app.core.templates import templates
from app.features.kinds import KINDS
from app.features.models import Choice
from app.features.service import (
    applicable_choice,
    choice_level_label,
    remove_inapplicable_picks,
)

router = APIRouter(tags=["features"])


def _get_choice(db: Session, character: Character, choice_id: int) -> Choice:
    choice = applicable_choice(db, character, choice_id)
    if choice is None:
        raise HTTPException(status_code=404)
    return choice


def _render_form(request, db, character, choice, selected, error=None, status_code=200):
    options = KINDS[choice.kind].options(db, choice)
    return templates.TemplateResponse(
        request,
        "features/partials/choice_form.html",
        {
            "character": character,
            "choice": choice,
            "level_label": choice_level_label(db, choice),
            "options": options,
            # Spell choices get filters; the schools listed are the ones among the options.
            "filter_schools": sorted({o.school for o in options if o.school}),
            "known": KINDS[choice.kind].already_have(db, choice, character.id),
            "known_label": KINDS[choice.kind].known_label,
            "noun": KINDS[choice.kind].noun,
            "selected": selected,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/characters/{character_id}/choices/{choice_id}", response_class=HTMLResponse)
def choice_form(request: Request, db: DbSession, character: OwnedCharacter, choice_id: int):
    choice = _get_choice(db, character, choice_id)
    picked = KINDS[choice.kind].picked(db, choice, character.id)
    return _render_form(request, db, character, choice, [o.slug for o in picked])


@router.post("/characters/{character_id}/choices/{choice_id}")
def save_choice(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    choice_id: int,
    picks: Annotated[list[str], Form()] = [],
):
    choice = _get_choice(db, character, choice_id)
    picks = list(dict.fromkeys(picks))  # drop duplicates, keep order

    if len(picks) != choice.count:
        wanted = "one" if choice.count == 1 else f"exactly {choice.count}"
        error = f"Choose {wanted}." + (f" You picked {len(picks)}." if picks else "")
    else:
        error = KINDS[choice.kind].save(db, choice, character.id, picks)

    if error:
        return _render_form(request, db, character, choice, picks, error, status_code=400)
    # A new pick can make others stale, e.g. switching subclass drops the old one's picks.
    remove_inapplicable_picks(db, character)
    db.commit()
    return refresh_character_page(request, db, user, character)

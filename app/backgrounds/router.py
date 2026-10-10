from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.backgrounds.models import Background
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.characters.page import refresh_character_page
from app.content.queries import available
from app.core.db import DbSession
from app.core.templates import templates
from app.features.kinds import OptionView
from app.features.service import fill_fixed_choices, remove_inapplicable_picks
from app.sheet.service import max_hp, track_max_change

router = APIRouter(tags=["backgrounds"])


def _render_form(
    request: Request,
    db: Session,
    character: Character,
    selected: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    backgrounds = db.scalars(
        select(Background).where(available(Background)).order_by(Background.name)
    ).all()
    options = [
        OptionView(str(b.id), b.name, b.summary, detail=f"Origin feat: {b.feat.name}")
        for b in backgrounds
    ]
    return templates.TemplateResponse(
        request,
        "backgrounds/partials/background_form.html",
        {
            "character": character,
            "options": options,
            "selected": selected,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/characters/{character_id}/background", response_class=HTMLResponse)
def background_form(request: Request, db: DbSession, character: OwnedCharacter):
    return _render_form(request, db, character, str(character.background_id or ""))


@router.post("/characters/{character_id}/background")
def save_background(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    background_id: Annotated[str, Form()] = "",
):
    background = db.get(Background, int(background_id)) if background_id.isdigit() else None
    if background is None or background.retired_at is not None:
        return _render_form(
            request, db, character, background_id, "Choose a background.", status_code=400
        )
    if background.id == character.background_id:
        return refresh_character_page(request, db, user, character)

    old_max = max_hp(db, character)
    character.background_id = background.id
    db.flush()
    db.refresh(character)  # reload the background relationship the rules below read
    # The old background's skills, ability increases and feat picks go with it.
    remove_inapplicable_picks(db, character)
    db.commit()
    fill_fixed_choices(db, character)
    track_max_change(db, character, old_max, heal=True)
    db.commit()
    return refresh_character_page(request, db, user, character)

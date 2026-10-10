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
from app.characters.service import change_origin
from app.content.queries import available
from app.core.db import DbSession
from app.core.templates import templates
from app.features.kinds import OptionView

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
    return templates.TemplateResponse(
        request,
        "characters/partials/origin_form.html",
        {
            "character": character,
            "title": "Background",
            "url": f"/characters/{character.id}/background",
            "field": "background_id",
            "options": [
                OptionView(str(b.id), b.name, b.summary, detail=f"Origin feat: {b.feat.name}")
                for b in backgrounds
            ],
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
    if background.id != character.background_id:
        change_origin(db, character, "background_id", background.id)
    return refresh_character_page(request, db, user, character)

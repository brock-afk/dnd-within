from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.characters.page import refresh_character_page
from app.characters.service import change_origin
from app.content.queries import available
from app.core.db import DbSession
from app.core.templates import templates
from app.features.kinds import OptionView
from app.species.models import Species

router = APIRouter(tags=["species"])


def _render_form(
    request: Request,
    db: Session,
    character: Character,
    selected: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    all_species = db.scalars(select(Species).where(available(Species)).order_by(Species.name)).all()
    return templates.TemplateResponse(
        request,
        "characters/partials/origin_form.html",
        {
            "character": character,
            "title": "Species",
            "url": f"/characters/{character.id}/species",
            "field": "species_id",
            "options": [
                OptionView(str(s.id), s.name, s.summary, detail=f"Speed {s.speed} ft")
                for s in all_species
            ],
            "selected": selected,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/characters/{character_id}/species", response_class=HTMLResponse)
def species_form(request: Request, db: DbSession, character: OwnedCharacter):
    return _render_form(request, db, character, str(character.species_id))


@router.post("/characters/{character_id}/species")
def save_species(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    species_id: Annotated[str, Form()] = "",
):
    species = db.get(Species, int(species_id)) if species_id.isdigit() else None
    if species is None or species.retired_at is not None:
        return _render_form(
            request, db, character, species_id, "Choose a species.", status_code=400
        )
    if species.id != character.species_id:
        change_origin(db, character, "species_id", species.id)
    return refresh_character_page(request, db, user, character)

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import CurrentUser
from app.characters import page
from app.characters.dependencies import OwnedCharacter
from app.characters.origins import SPECIES
from app.characters.queries import origin_form_view, refreshed_build_view
from app.characters.service import choose_origin
from app.core.db import DbSession

router = APIRouter(tags=["species"])


@router.get("/characters/{character_id}/species", response_class=HTMLResponse)
def species_form(request: Request, db: DbSession, character: OwnedCharacter):
    return page.origin_form(request, origin_form_view(db, character, SPECIES))


@router.post("/characters/{character_id}/species")
def save_species(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    species_id: Annotated[str, Form()] = "",
):
    if error := choose_origin(db, character, SPECIES, species_id):
        view = origin_form_view(db, character, SPECIES, selected=species_id)
        return page.origin_form(request, view, error)
    return page.refresh_build(request, refreshed_build_view(db, user, character))

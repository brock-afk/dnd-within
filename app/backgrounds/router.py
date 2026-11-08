from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import CurrentUser
from app.characters import page
from app.characters.dependencies import OwnedCharacter
from app.characters.origins import BACKGROUND
from app.characters.queries import origin_form_view, refreshed_build_view
from app.characters.service import choose_origin
from app.core.db import DbSession

router = APIRouter(tags=["backgrounds"])


@router.get("/characters/{character_id}/background", response_class=HTMLResponse)
def background_form(request: Request, db: DbSession, character: OwnedCharacter):
    return page.origin_form(request, origin_form_view(db, character, BACKGROUND))


@router.post("/characters/{character_id}/background")
def save_background(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    background_id: Annotated[str, Form()] = "",
):
    if error := choose_origin(db, character, BACKGROUND, background_id):
        view = origin_form_view(db, character, BACKGROUND, selected=background_id)
        return page.origin_form(request, view, error)
    return page.refresh_build(request, refreshed_build_view(db, user, character))

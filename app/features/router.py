from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import CurrentUser
from app.characters import page as characters_page
from app.characters.dependencies import OwnedCharacter
from app.characters.queries import refreshed_build_view
from app.core.db import DbSession
from app.features import page, service
from app.features.dependencies import GridChoice
from app.features.queries import choice_form_view

router = APIRouter(tags=["features"])


@router.get("/characters/{character_id}/choices/{choice_id}", response_class=HTMLResponse)
def choice_form(request: Request, db: DbSession, character: OwnedCharacter, choice: GridChoice):
    return page.choice_form(request, choice_form_view(db, character, choice))


@router.post("/characters/{character_id}/choices/{choice_id}")
def save_choice(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    choice: GridChoice,
    picks: Annotated[list[str], Form()] = [],
):
    if error := service.save_choice(db, character, choice, picks):
        view = choice_form_view(db, character, choice, selected=picks)
        return page.choice_form(request, view, error)
    return characters_page.refresh_build(request, refreshed_build_view(db, user, character))

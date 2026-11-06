from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import CurrentUser
from app.characters import page as characters_page
from app.characters.dependencies import OwnedCharacter
from app.characters.queries import refreshed_build_view
from app.core.db import DbSession
from app.leveling import page, service
from app.leveling.queries import level_up_view

router = APIRouter(tags=["leveling"])


@router.get("/characters/{character_id}/level-up", response_class=HTMLResponse)
def level_up_panel(request: Request, db: DbSession, character: OwnedCharacter):
    return page.level_up_panel(request, level_up_view(db, character))


@router.post("/characters/{character_id}/level-up")
def level_up(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    level: Annotated[str, Form()] = "",  # the level the page showed
    hp_method: Annotated[str, Form()] = "",
    hp_roll: Annotated[str, Form()] = "",
):
    if error := service.level_up(db, character, level, hp_method, hp_roll):
        view = level_up_view(db, character, hp_roll.strip())
        return page.level_up_panel(request, view, error)
    return characters_page.refresh_build(request, refreshed_build_view(db, user, character))


@router.post("/characters/{character_id}/level-down")
def level_down(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    level: Annotated[str, Form()] = "",  # the level the page showed
):
    # Every error means the page was stale (the button only shows above level 1), and the
    # refreshed page shows the real level.
    service.level_down(db, character, level)
    return characters_page.refresh_build(request, refreshed_build_view(db, user, character))

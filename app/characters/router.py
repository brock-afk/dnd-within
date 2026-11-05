from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import CurrentUser
from app.characters import page
from app.characters.dependencies import OwnedCharacter
from app.characters.form import CharacterForm
from app.characters.queries import build_page_view, character_list_view, new_character_view
from app.characters.service import create_character, delete_character, rename
from app.core.db import DbSession
from app.core.templates import hx_redirect

router = APIRouter(tags=["characters"])


@router.get("/")
def index():
    return RedirectResponse("/characters", status_code=303)


@router.get("/characters", response_class=HTMLResponse)
def list_characters(request: Request, db: DbSession, user: CurrentUser):
    return page.character_list(request, character_list_view(db, user))


@router.get("/characters/new", response_class=HTMLResponse)
def new_character(request: Request, db: DbSession, user: CurrentUser):
    return page.new_character(request, new_character_view(db, user))


@router.post("/characters")
def create(
    request: Request, db: DbSession, user: CurrentUser, form: Annotated[CharacterForm, Form()]
):
    character, errors = create_character(db, user, form)
    if errors:
        return page.new_character_form(request, new_character_view(db, user), form, errors)
    return hx_redirect(f"/characters/{character.id}")


@router.get("/characters/{character_id}", response_class=HTMLResponse)
def show_character(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    return page.build_page(request, build_page_view(db, user, character))


@router.get("/characters/{character_id}/name", response_class=HTMLResponse)
def name_heading(request: Request, character: OwnedCharacter):
    return page.name_heading(request, character)


@router.get("/characters/{character_id}/name/edit", response_class=HTMLResponse)
def edit_name(request: Request, character: OwnedCharacter):
    return page.name_form(request, character, character.name)


@router.post("/characters/{character_id}/name", response_class=HTMLResponse)
def rename_character(
    request: Request, character: OwnedCharacter, name: Annotated[str, Form()] = ""
):
    if error := rename(character, name):
        return page.name_form(request, character, name, error)
    return page.name_heading(request, character)


@router.post("/characters/{character_id}/delete")
def delete(
    request: Request, db: DbSession, character: OwnedCharacter, confirm: Annotated[str, Form()] = ""
):
    if error := delete_character(db, character, confirm):
        return page.delete_form(request, character, confirm, error)
    return hx_redirect("/characters")

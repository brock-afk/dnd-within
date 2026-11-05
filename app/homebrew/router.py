from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import CurrentUser
from app.auth.models import User
from app.core.db import DbSession
from app.core.templates import hx_redirect
from app.homebrew import page
from app.homebrew.dependencies import OwnedHomebrewItem, get_owned_item
from app.homebrew.form import ItemForm
from app.homebrew.queries import (
    edit_item_view,
    editor_view,
    library_view,
    new_item_view,
    opened_from,
)
from app.homebrew.service import delete_item, save_from_form
from app.inventory.models import Item

router = APIRouter(tags=["homebrew"])


@router.get("/homebrew", response_class=HTMLResponse)
def library(request: Request, db: DbSession, user: CurrentUser):
    return page.library(request, library_view(db, user))


@router.get("/homebrew/items/new", response_class=HTMLResponse)
def new_item(request: Request, db: DbSession, user: CurrentUser, character: str = ""):
    return page.editor_page(request, new_item_view(db, user, character))


@router.get("/homebrew/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item(request: Request, db: DbSession, user: CurrentUser, item: OwnedHomebrewItem):
    return page.editor_page(request, edit_item_view(db, user, item))


@router.post("/homebrew/items/preview", response_class=HTMLResponse)
def preview(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    form: Annotated[ItemForm, Form()],
):
    """Redraw the editor with a spell or ability row added or removed, keeping what's typed."""
    # The item comes from the form, not the URL, so the dependency is called by hand.
    item = get_owned_item(int(form.item_id), db, user) if form.item_id.isdigit() else None
    form.edit_rows()
    return page.editor_form(request, editor_view(db, user, form, item))


def _save(request: Request, db: DbSession, user: User, form: ItemForm, item: Item | None):
    character = opened_from(db, user, form.character)
    if errors := save_from_form(db, user, form, item, character):
        view = editor_view(db, user, form, item)
        return page.editor_form(request, view, errors)
    return hx_redirect(f"/characters/{character.id}/sheet" if character else "/homebrew")


@router.post("/homebrew/items")
def create_item(
    request: Request, db: DbSession, user: CurrentUser, form: Annotated[ItemForm, Form()]
):
    return _save(request, db, user, form, None)


@router.post("/homebrew/items/{item_id}")
def update_item(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    item: OwnedHomebrewItem,
    form: Annotated[ItemForm, Form()],
):
    return _save(request, db, user, form, item)


@router.get("/homebrew/items/{item_id}/delete", response_class=HTMLResponse)
def delete_confirm(request: Request, item: OwnedHomebrewItem):
    return page.delete_confirm(request, item)


@router.post("/homebrew/items/{item_id}/delete")
def delete(db: DbSession, item: OwnedHomebrewItem):
    delete_item(db, item)
    return hx_redirect("/homebrew")

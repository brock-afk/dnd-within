from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.auth.models import User
from app.characters.models import Character
from app.content.queries import available, visible
from app.core.db import DbSession
from app.core.templates import hx_redirect, templates
from app.homebrew.form import (
    ABILITIES,
    ACTIONS,
    CATEGORIES,
    DAMAGE_TYPES,
    PREPARED,
    RARITIES,
    RECHARGES,
    TOOL_MODES,
    ItemForm,
    build_item_def,
)
from app.homebrew.service import delete_item, owned_item, save_item, user_items
from app.inventory.models import Item
from app.inventory.rules import TOOLS
from app.inventory.service import add_item, item_detail
from app.spells.models import Spell

router = APIRouter(tags=["homebrew"])


def _character(db: Session, user: User, key: str) -> Character | None:
    """The character the editor was opened from (Add item), if it's the user's."""
    character = db.get(Character, int(key)) if key.isdigit() else None
    return character if character is not None and character.user_id == user.id else None


def _form_context(db: Session, user: User, form: ItemForm, item: Item | None, errors=None) -> dict:
    spells = db.scalars(
        select(Spell).where(available(Spell), visible(Spell, user.id)).order_by(Spell.level, Spell.name)
    ).all()
    return {
        "user": user,
        "form": form,
        "item": item,
        "errors": errors or {},
        "character": _character(db, user, form.character),
        "spells": spells,
        "categories": CATEGORIES,
        "rarities": RARITIES,
        "recharges": RECHARGES,
        "prepared": PREPARED,
        "actions": ACTIONS,
        "tool_modes": TOOL_MODES,
        "tools": TOOLS,
        "abilities": ABILITIES,
        "damage_types": DAMAGE_TYPES,
    }


def _render_form(request, db, user, form, item, errors=None, status_code=200):
    return templates.TemplateResponse(
        request,
        "homebrew/partials/item_form.html",
        _form_context(db, user, form, item, errors),
        status_code=status_code,
    )


def _render_page(request, db, user, form, item):
    return templates.TemplateResponse(
        request, "homebrew/edit.html", _form_context(db, user, form, item)
    )


def _owned(db: Session, user: User, item_id: int) -> Item:
    item = owned_item(db, user, item_id)
    if item is None:
        raise HTTPException(status_code=404)
    return item


@router.get("/homebrew", response_class=HTMLResponse)
def library(request: Request, db: DbSession, user: CurrentUser):
    items = [(item, item_detail(item)) for item in user_items(db, user)]
    return templates.TemplateResponse(
        request, "homebrew/list.html", {"user": user, "items": items}
    )


@router.get("/homebrew/items/new", response_class=HTMLResponse)
def new_item(request: Request, db: DbSession, user: CurrentUser, character: str = ""):
    form = ItemForm(character=character if _character(db, user, character) else "")
    return _render_page(request, db, user, form, None)


@router.get("/homebrew/items/{item_id}/edit", response_class=HTMLResponse)
def edit_item(request: Request, db: DbSession, user: CurrentUser, item_id: int):
    item = _owned(db, user, item_id)
    form = ItemForm(**(item.definition or {})).upgrade()
    return _render_page(request, db, user, form, item)


@router.post("/homebrew/items/preview", response_class=HTMLResponse)
def preview(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    form: Annotated[ItemForm, Form()],
):
    """Redraw the editor with a spell or ability row added or removed, keeping what's typed."""
    item = _owned(db, user, int(form.item_id)) if form.item_id.isdigit() else None
    form.edit_rows()
    return _render_form(request, db, user, form, item)


def _save(request, db, user, form: ItemForm, item: Item | None):
    item_def, errors = build_item_def(db, form)
    if errors:
        return _render_form(request, db, user, form, item, errors, status_code=400)
    character = _character(db, user, form.character)
    saved = save_item(db, user, item_def, form.definition(), item)
    if character is not None:
        add_item(db, character, saved, 1)
        db.commit()
        return hx_redirect(f"/characters/{character.id}/sheet")
    db.commit()
    return hx_redirect("/homebrew")


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
    item_id: int,
    form: Annotated[ItemForm, Form()],
):
    return _save(request, db, user, form, _owned(db, user, item_id))


@router.get("/homebrew/items/{item_id}/delete", response_class=HTMLResponse)
def delete_confirm(request: Request, db: DbSession, user: CurrentUser, item_id: int):
    """Asks before deleting, in place of the item's buttons."""
    return templates.TemplateResponse(
        request, "homebrew/partials/delete_confirm.html", {"item": _owned(db, user, item_id)}
    )


@router.post("/homebrew/items/{item_id}/delete")
def delete(db: DbSession, user: CurrentUser, item_id: int):
    delete_item(db, _owned(db, user, item_id))
    db.commit()
    return hx_redirect("/homebrew")

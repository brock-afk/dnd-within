"""Rendering the homebrew pages from their view models (app/homebrew/queries.py), including
the editor's errors. Nothing here touches the database."""

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.templates import templates
from app.homebrew.form import (
    ABILITIES,
    ACTIONS,
    CATEGORIES,
    DAMAGE_TYPES,
    PREPARED,
    RARITIES,
    RECHARGES,
    TOOL_MODES,
)
from app.homebrew.queries import EditorView, LibraryView
from app.inventory.models import Item
from app.inventory.rules import TOOLS

# The editor's fixed choices.
EDITOR_OPTIONS = {
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


def library(request: Request, view: LibraryView) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "homebrew/list.html", {"user": view.user, "items": view.items}
    )


def _editor_context(view: EditorView, errors: dict[str, str] | None) -> dict:
    return {
        "user": view.user,
        "form": view.form,
        "item": view.item,
        "character": view.character,
        "spells": view.spells,
        "errors": errors or {},
        **EDITOR_OPTIONS,
    }


def editor_page(request: Request, view: EditorView) -> HTMLResponse:
    """The editor as a full page, opened from the library or a character's Add item."""
    return templates.TemplateResponse(request, "homebrew/edit.html", _editor_context(view, None))


def editor_form(
    request: Request,
    view: EditorView,
    *,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    """Just the editor's form, swapped in place: after adding or removing a row, or to show
    `errors` ({field: problem}) next to their fields."""
    return templates.TemplateResponse(
        request,
        "homebrew/partials/item_form.html",
        _editor_context(view, errors),
        status_code=status_code,
    )


def delete_confirm(request: Request, item: Item) -> HTMLResponse:
    """Asks before deleting, in place of the item's buttons."""
    return templates.TemplateResponse(
        request, "homebrew/partials/delete_confirm.html", {"item": item}
    )

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.templates import templates, view_context
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
    return templates.TemplateResponse(request, "homebrew/list.html", view_context(view))


def _editor_context(view: EditorView, errors: dict[str, str] | None) -> dict:
    return view_context(view, errors=errors or {}, **EDITOR_OPTIONS)


def editor_page(request: Request, view: EditorView) -> HTMLResponse:
    return templates.TemplateResponse(request, "homebrew/edit.html", _editor_context(view, None))


def editor_form(
    request: Request, view: EditorView, errors: dict[str, str] | None = None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "homebrew/partials/item_form.html",
        _editor_context(view, errors),
        status_code=400 if errors else 200,
    )


def delete_confirm(request: Request, item: Item) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "homebrew/partials/delete_confirm.html", {"item": item}
    )

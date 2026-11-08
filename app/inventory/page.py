from fastapi import Request
from fastapi.responses import HTMLResponse

from app.characters.models import Character
from app.core.templates import templates, view_context
from app.inventory.models import CharacterItem
from app.inventory.queries import AddConfirmView, CoinsBlockView, CoinsFormView, ItemSearchView
from app.inventory.rules import COINS


def _partial(request: Request, name: str, context: dict, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request, f"inventory/partials/{name}.html", context, status_code=400 if error else 200
    )


def add_panel(request: Request, character: Character, view: ItemSearchView) -> HTMLResponse:
    return _partial(request, "add_panel", view_context(view, character=character))


def add_results(request: Request, character: Character, view: ItemSearchView) -> HTMLResponse:
    return _partial(request, "add_results", view_context(view, character=character))


def add_confirm(
    request: Request, character: Character, view: AddConfirmView, error: str | None = None
) -> HTMLResponse:
    context = view_context(view, character=character, error=error)
    return _partial(request, "add_confirm", context, error)


def remove_confirm(request: Request, character: Character, row: CharacterItem) -> HTMLResponse:
    return _partial(request, "remove_confirm", {"character": character, "row": row})


def coins_block(
    request: Request, character: Character, view: CoinsBlockView, error: str | None = None
) -> HTMLResponse:
    context = view_context(view, character=character, coin_labels=COINS, coin_error=error)
    return _partial(request, "coins_block", context, error)


def coins_form(
    request: Request, character: Character, view: CoinsFormView, error: str | None = None
) -> HTMLResponse:
    context = view_context(view, character=character, coin_labels=COINS, error=error)
    return _partial(request, "coins_form", context, error)

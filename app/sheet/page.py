from fastapi import Request
from fastapi.responses import HTMLResponse

from app.characters.models import Character
from app.core.templates import morph_in_place, templates, view_context
from app.inventory.rules import COINS, MAX_ATTUNED
from app.sheet.queries import CopyConfirmView, CopySearchView, PreparedEditorView, SheetView

SHEET_SELECTOR = "#sheet-page"
ACTION_LABELS = {"action": "Action", "bonus_action": "Bonus Action", "reaction": "Reaction"}


def sheet(
    request: Request,
    view: SheetView,
    errors: dict[str, str] | None = None,
    notices: dict[str, str] | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sheet/sheet.html",
        view_context(
            view,
            action_labels=ACTION_LABELS,
            coin_labels=COINS,
            max_attuned=MAX_ATTUNED,
            errors=errors or {},
            notices=notices or {},
        ),
        status_code=400 if errors else 200,
    )


def refresh_sheet(
    request: Request,
    view: SheetView,
    errors: dict[str, str] | None = None,
    notices: dict[str, str] | None = None,
) -> HTMLResponse:
    return morph_in_place(sheet(request, view, errors, notices), SHEET_SELECTOR)


def prepared_editor(
    request: Request, view: PreparedEditorView, error: str | None = None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sheet/partials/prepared_editor.html",
        view_context(view, error=error),
        status_code=400 if error else 200,
    )


def copy_results(request: Request, character: Character, view: CopySearchView) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "sheet/partials/copy_results.html", {"character": character, "copy": view}
    )


def copy_confirm(request: Request, character: Character, view: CopyConfirmView) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "sheet/partials/copy_confirm.html",
        {"character": character, "errors": {}, "copy_confirm": view},
    )

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.templates import morph_in_place, templates, view_context
from app.inventory.queries import COINS, MAX_ATTUNED
from app.sheet.queries import SheetView

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
    # Morphing keeps the scroll position and focus, unlike a full page load.
    return morph_in_place(sheet(request, view, errors, notices), SHEET_SELECTOR)

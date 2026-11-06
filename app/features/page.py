"""Rendering the choice form from its view model (app/features/queries.py)."""

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.templates import templates, view_context
from app.features.queries import ChoiceFormView


def choice_form(request: Request, view: ChoiceFormView, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "features/partials/choice_form.html",
        view_context(view, error=error),
        status_code=400 if error else 200,
    )

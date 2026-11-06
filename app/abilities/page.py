"""Rendering the score editor and the increase editor from their view models
(app/abilities/queries.py)."""

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.abilities.queries import AbilityEditorView, IncreaseView
from app.core.templates import templates, view_context


def ability_editor(request: Request, view: AbilityEditorView) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "abilities/partials/ability_form.html",
        view_context(view),
        status_code=400 if view.errors else 200,
    )


def increase_editor(request: Request, view: IncreaseView, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "abilities/partials/increase_form.html",
        view_context(view, error=error),
        status_code=400 if error else 200,
    )

"""Rendering the level-up panel from its view model (app/leveling/queries.py)."""

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.core.templates import templates, view_context
from app.leveling.queries import LevelUpView


def level_up_panel(request: Request, view: LevelUpView, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "leveling/partials/level_up.html",
        view_context(view, error=error),
        status_code=400 if error else 200,
    )

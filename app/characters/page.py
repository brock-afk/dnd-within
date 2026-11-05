"""Rendering the character pages from their view models (app/characters/queries.py), in full
or as an in-place refresh. Nothing here touches the database.

Routes that change a character (choices, ability scores, levels) return `refresh_build`, so
htmx morphs the updated page into place: the scroll position and focus stay where they were,
instead of jumping to the top like a full page load.
"""

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.characters.form import CharacterForm
from app.characters.models import Character
from app.characters.queries import (
    BuildPageView,
    CharacterListView,
    NewCharacterView,
    OriginFormView,
)
from app.core.templates import morph_in_place, templates, view_context

# The element in characters/show.html that a refresh replaces.
PAGE_SELECTOR = "#character-page"


def character_list(request: Request, view: CharacterListView) -> HTMLResponse:
    return templates.TemplateResponse(request, "characters/list.html", view_context(view))


def new_character(request: Request, view: NewCharacterView) -> HTMLResponse:
    return templates.TemplateResponse(request, "characters/new.html", view_context(view))


def new_character_form(
    request: Request, view: NewCharacterView, form: CharacterForm, errors: dict[str, str]
) -> HTMLResponse:
    """The whole form again, so every problem shows next to its field, with the entries
    kept."""
    return templates.TemplateResponse(
        request,
        "characters/partials/form.html",
        view_context(view, errors=errors, values=form),
        status_code=400,
    )


def build_page(request: Request, view: BuildPageView) -> HTMLResponse:
    return templates.TemplateResponse(request, "characters/show.html", view_context(view))


def refresh_build(request: Request, view: BuildPageView) -> HTMLResponse:
    """The full page, with headers telling htmx to morph just the page body into place,
    whatever element sent the request."""
    return morph_in_place(build_page(request, view), PAGE_SELECTOR)


def name_heading(request: Request, character: Character) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "characters/partials/name_heading.html", {"character": character}
    )


def name_form(
    request: Request, character: Character, value: str, error: str | None = None
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "characters/partials/name_form.html",
        {"character": character, "value": value, "error": error},
        status_code=400 if error else 200,
    )


def delete_form(request: Request, character: Character, value: str, error: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "characters/partials/delete_form.html",
        {"character": character, "value": value, "error": error},
        status_code=400,
    )


def origin_form(request: Request, view: OriginFormView, error: str | None = None) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "characters/partials/origin_form.html",
        view_context(view, error=error),
        status_code=400 if error else 200,
    )

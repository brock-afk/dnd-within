"""The ability score editor, and the editor for ability score increases: any feature's
`ability_scores` choice (a background's +2/+1 or +1/+1/+1)."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.abilities import page, service
from app.abilities.dependencies import IncreaseChoice
from app.abilities.form import AbilityForm, IncreaseForm
from app.abilities.queries import ability_editor_view, increase_view, saved_editor_view
from app.auth.dependencies import CurrentUser
from app.characters import page as characters_page
from app.characters.dependencies import OwnedCharacter
from app.characters.queries import refreshed_build_view
from app.core.db import DbSession

router = APIRouter(tags=["abilities"])


@router.get("/characters/{character_id}/abilities/edit", response_class=HTMLResponse)
def edit_abilities(request: Request, character: OwnedCharacter, method: str = ""):
    return page.ability_editor(request, saved_editor_view(character, method))


@router.post("/characters/{character_id}/abilities/preview", response_class=HTMLResponse)
def preview_abilities(
    request: Request, character: OwnedCharacter, form: Annotated[AbilityForm, Form()]
):
    """Redraw the editor after a stepper click or a changed value: modifiers, costs, and
    which buttons are enabled all come from the server."""
    view = ability_editor_view(
        character, form.editor_method, form.previewed_scores(), form.roll_values()
    )
    return page.ability_editor(request, view)


@router.post("/characters/{character_id}/abilities")
def save_abilities(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    form: Annotated[AbilityForm, Form()],
):
    if errors := service.save_scores(db, character, form):
        view = ability_editor_view(
            character, form.editor_method, form.scores(), form.roll_values(), errors
        )
        return page.ability_editor(request, view)
    return characters_page.refresh_build(request, refreshed_build_view(db, user, character))


@router.post(
    "/characters/{character_id}/ability-increases/{choice_id}/preview",
    response_class=HTMLResponse,
)
def preview_increases(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    choice: IncreaseChoice,
    form: Annotated[IncreaseForm, Form()],
):
    form.resolve_clash()
    return page.increase_editor(request, increase_view(db, character, choice, form))


@router.post("/characters/{character_id}/ability-increases/{choice_id}")
def save_increases(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    choice: IncreaseChoice,
    form: Annotated[IncreaseForm, Form()],
):
    if error := service.save_increase(db, character, choice, form):
        return page.increase_editor(request, increase_view(db, character, choice, form), error)
    return characters_page.refresh_build(request, refreshed_build_view(db, user, character))

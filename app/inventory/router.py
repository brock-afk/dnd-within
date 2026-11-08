from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.core.db import DbSession
from app.inventory import page, service
from app.inventory.dependencies import (
    AcScroll,
    CatalogItem,
    HealingItem,
    OwnedItemRow,
    PostedCatalogItem,
)
from app.inventory.form import CoinChangeForm, CoinForm
from app.inventory.queries import (
    add_confirmation,
    coins_block_view,
    coins_form_view,
    item_search,
)
from app.sheet import page as sheet_page
from app.sheet.queries import refreshed_sheet_view

router = APIRouter(tags=["inventory"])

BASE = "/characters/{character_id}/sheet/inventory"


# --- Adding from the catalog --------------------------------------------------------------


@router.get(BASE + "/add", response_class=HTMLResponse)
def add_panel(request: Request, db: DbSession, character: OwnedCharacter, q: str = ""):
    """Add an item, like copying a spell: search by name, pick one, confirm. `q` refills the
    search when coming back from the confirm step."""
    return page.add_panel(request, character, item_search(db, character, q))


@router.get(BASE + "/add/search", response_class=HTMLResponse)
def add_search(request: Request, db: DbSession, character: OwnedCharacter, q: str = ""):
    return page.add_results(request, character, item_search(db, character, q))


@router.get(BASE + "/add/confirm", response_class=HTMLResponse)
def add_confirm(
    request: Request, db: DbSession, character: OwnedCharacter, item: CatalogItem, q: str = ""
):
    return page.add_confirm(request, character, add_confirmation(db, character, item, q))


@router.post(BASE + "/add", response_class=HTMLResponse)
def add(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    item: PostedCatalogItem,
    quantity: Annotated[str, Form()] = "1",
    spell_id: Annotated[str, Form()] = "",
    q: Annotated[str, Form()] = "",
):
    if error := service.add_from_catalog(db, character, item, quantity, spell_id):
        view = add_confirmation(db, character, item, q, quantity, spell_id)
        return page.add_confirm(request, character, view, error)
    return sheet_page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


# --- Carried items ------------------------------------------------------------------------


@router.post(BASE + "/{row_id}/quantity", response_class=HTMLResponse)
def quantity(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    row: OwnedItemRow,
    delta: Annotated[str, Form()] = "",
):
    error = service.change_quantity(db, row, delta)
    view = refreshed_sheet_view(db, user, character)
    return sheet_page.refresh_sheet(request, view, {"inventory": error} if error else None)


@router.post(BASE + "/{row_id}/use", response_class=HTMLResponse)
def use(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, row: OwnedItemRow
):
    """Spend one of a consumable (drink the potion, read the scroll)."""
    error = service.use_item(db, row)
    view = refreshed_sheet_view(db, user, character)
    return sheet_page.refresh_sheet(request, view, {"inventory": error} if error else None)


@router.post(BASE + "/{row_id}/heal", response_class=HTMLResponse)
def heal_with(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    use: HealingItem,
):
    outcome = service.heal_with(db, character, use)
    view = refreshed_sheet_view(db, user, character)
    if outcome.error:
        return sheet_page.refresh_sheet(request, view, {"hp": outcome.error})
    return sheet_page.refresh_sheet(request, view, notices={"hp": outcome.notice})


@router.post(BASE + "/{row_id}/cast-ac", response_class=HTMLResponse)
def cast_ac_scroll(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, row: AcScroll
):
    """Read a scroll of an AC spell (Mage Armor) from the AC card: its effect starts and the
    scroll is used up."""
    error = service.cast_ac_scroll(db, character, row)
    view = refreshed_sheet_view(db, user, character)
    return sheet_page.refresh_sheet(request, view, {"ac_effect": error} if error else None)


@router.post(BASE + "/{row_id}/attune", response_class=HTMLResponse)
def attune(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    row: OwnedItemRow,
    attuned: Annotated[str, Form()] = "",
):
    error = service.attune(db, character, row, attuned)
    view = refreshed_sheet_view(db, user, character)
    return sheet_page.refresh_sheet(request, view, {"inventory": error} if error else None)


@router.post(BASE + "/{row_id}/notes", response_class=HTMLResponse)
def notes(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    row: OwnedItemRow,
    notes: Annotated[str, Form()] = "",
):
    service.set_notes(db, row, notes)
    return sheet_page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


@router.get(BASE + "/{row_id}/remove", response_class=HTMLResponse)
def remove_confirm(request: Request, character: OwnedCharacter, row: OwnedItemRow):
    """Asks before removing, in place of the row's buttons."""
    return page.remove_confirm(request, character, row)


@router.post(BASE + "/{row_id}/remove", response_class=HTMLResponse)
def remove(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, row: OwnedItemRow
):
    service.remove_item(db, character, row)
    return sheet_page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


# --- Coins --------------------------------------------------------------------------------


@router.post(BASE + "/coins/change", response_class=HTMLResponse)
def change_coins(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    form: Annotated[CoinChangeForm, Form()],
):
    if error := service.change_coins(db, character, form):
        view = coins_block_view(db, character, form.amount, form.coin)
        return page.coins_block(request, character, view, error)
    return sheet_page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


@router.get(BASE + "/coins/edit", response_class=HTMLResponse)
def edit_coins(request: Request, db: DbSession, character: OwnedCharacter):
    return page.coins_form(request, character, coins_form_view(db, character))


@router.post(BASE + "/coins", response_class=HTMLResponse)
def coins(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    form: Annotated[CoinForm, Form()],
):
    if error := service.save_coins(db, character, form):
        view = coins_form_view(db, character, form.model_dump())
        return page.coins_form(request, character, view, error)
    return sheet_page.refresh_sheet(request, refreshed_sheet_view(db, user, character))

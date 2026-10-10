from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.content.queries import available, visible
from app.core.db import DbSession
from app.core.templates import templates
from app.features.service import remove_inapplicable_picks
from app.inventory.models import CharacterItem, Item
from app.inventory.service import (
    COINS,
    MAX_COINS,
    SEARCH_MIN_LENGTH,
    ac_scrolls,
    add_item,
    change_quantity,
    character_item,
    coin_summary,
    coin_values,
    healing_uses,
    item_detail,
    pack_contents,
    scroll_spells,
    search_items,
    set_attuned,
    set_coins,
    use_one,
)
from app.inventory.rules import gain, spend
from app.sheet.rules import current_hp, heal, roll_detail, set_temp_hp
from app.sheet.service import apply_ac_spell, max_hp, play_state
from app.sheet.router import refresh_sheet
from app.spells.models import Spell

router = APIRouter(tags=["inventory"])

BASE = "/characters/{character_id}/sheet/inventory"


def _item_partial(request: Request, name: str, context: dict, status_code: int = 200):
    return templates.TemplateResponse(
        request, f"inventory/partials/{name}.html", context, status_code=status_code
    )


def _search_context(db: Session, character: Character, query: str) -> dict:
    return {
        "character": character,
        "query": query,
        "min_length": SEARCH_MIN_LENGTH,
        "results": [
            (item, item_detail(item)) for item in search_items(db, query, character.user_id)
        ],
    }


@router.get(BASE + "/add", response_class=HTMLResponse)
def add_panel(request: Request, db: DbSession, character: OwnedCharacter, q: str = ""):
    """Add an item, like copying a spell: search by name, pick one, confirm. `q` refills the
    search when coming back from the confirm step."""
    return _item_partial(request, "add_panel", _search_context(db, character, q))


@router.get(BASE + "/add/search", response_class=HTMLResponse)
def add_search(request: Request, db: DbSession, character: OwnedCharacter, q: str = ""):
    return _item_partial(request, "add_results", _search_context(db, character, q))


def _render_confirm(
    request: Request,
    db: Session,
    character: Character,
    item: Item,
    query: str,
    quantity: str = "1",
    spell_id: str = "",
    error: str | None = None,
    status_code: int = 200,
):
    """The confirm step: quantity, and the spell for a scroll; a pack lists what it adds."""
    return _item_partial(
        request,
        "add_confirm",
        {
            "character": character,
            "item": item,
            "detail": item_detail(item),
            "contents": pack_contents(db, item),
            "spells": scroll_spells(db, item) if item.category == "scroll" else [],
            "query": query,
            "quantity": quantity,
            "spell_id": spell_id,
            "error": error,
        },
        status_code=status_code,
    )


def _catalog_item(db: Session, key: str, user_id: int) -> Item | None:
    """An item that can be added: not retired, and published or this user's homebrew."""
    if not key.isdigit():
        return None
    return db.scalar(
        select(Item).where(Item.id == int(key), available(Item), visible(Item, user_id))
    )


@router.get(BASE + "/add/confirm", response_class=HTMLResponse)
def add_confirm(
    request: Request, db: DbSession, character: OwnedCharacter, item: str = "", q: str = ""
):
    found = _catalog_item(db, item, character.user_id)
    if found is None:
        raise HTTPException(status_code=404)
    return _render_confirm(request, db, character, found, q)


@router.post(BASE + "/add", response_class=HTMLResponse)
def add(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    item_id: Annotated[str, Form()] = "",
    quantity: Annotated[str, Form()] = "1",
    spell_id: Annotated[str, Form()] = "",
    q: Annotated[str, Form()] = "",
):
    item = _catalog_item(db, item_id, character.user_id)
    if item is None:
        raise HTTPException(status_code=404)
    spell = db.get(Spell, int(spell_id)) if spell_id.isdigit() else None
    amount = int(quantity) if quantity.strip().isdigit() else 0
    if not 1 <= amount <= 999:
        error = "Quantity is 1 to 999."
    else:
        error = add_item(db, character, item, amount, spell)
    if error:
        return _render_confirm(
            request, db, character, item, q, quantity, spell_id, error, status_code=400
        )
    db.commit()
    return refresh_sheet(request, db, user, character)


def _row(db: Session, character: Character, row_id: int) -> CharacterItem:
    row = character_item(db, character, row_id)
    if row is None:
        raise HTTPException(status_code=404)
    return row


@router.post(BASE + "/{row_id}/quantity", response_class=HTMLResponse)
def quantity(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    row_id: int,
    delta: Annotated[str, Form()] = "",
):
    if delta not in ("1", "-1"):
        raise HTTPException(status_code=400)
    change_quantity(db, _row(db, character, row_id), int(delta))
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post(BASE + "/{row_id}/use", response_class=HTMLResponse)
def use(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, row_id: int):
    """Spend one of a consumable (drink the potion, read the scroll)."""
    row = _row(db, character, row_id)
    if not row.item.consumable:
        return refresh_sheet(
            request, db, user, character, {"inventory": f"{row.name} isn't used up."}, 400
        )
    use_one(db, row)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post(BASE + "/{row_id}/heal", response_class=HTMLResponse)
def heal_with(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, row_id: int
):
    """Drink a potion or cast a healing scroll from the HP panel: roll its dice, heal (or gain
    temporary hit points), and use it up. The roll is shown in the panel."""
    row = _row(db, character, row_id)
    use = next((u for u in healing_uses([row])), None)
    maximum = max_hp(db, character)
    if use is None or maximum is None:
        raise HTTPException(status_code=400)
    amount, rolled = roll_detail(use.dice)
    state = play_state(db, character)
    name = row.name
    if use.temporary:
        if amount > state.temp_hp:
            set_temp_hp(state, amount, row.spell.name)
            notice = f"{name}: {amount} temporary hit points ({rolled})."
        else:
            notice = f"{name}: rolled {amount} ({rolled}); you kept your {state.temp_hp} temp HP."
    else:
        before = current_hp(state, maximum)
        heal(state, amount, maximum)
        gained = current_hp(state, maximum) - before
        notice = f"{name}: healed {gained} ({rolled})" + (
            f", {amount - gained} over your max." if gained < amount else "."
        )
    use_one(db, row)
    db.commit()
    return refresh_sheet(request, db, user, character, notices={"hp": notice})


@router.post(BASE + "/{row_id}/cast-ac", response_class=HTMLResponse)
def cast_ac_scroll(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, row_id: int
):
    """Read a scroll of an AC spell (Mage Armor) from the AC card: its effect starts and the
    scroll is used up."""
    row = _row(db, character, row_id)
    if not ac_scrolls([row]):
        raise HTTPException(status_code=400)
    apply_ac_spell(db, character, row.spell)
    use_one(db, row)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post(BASE + "/{row_id}/attune", response_class=HTMLResponse)
def attune(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    row_id: int,
    attuned: Annotated[str, Form()] = "",
):
    error = set_attuned(db, character, _row(db, character, row_id), attuned == "1")
    if error:
        return refresh_sheet(request, db, user, character, {"inventory": error}, 400)
    # Ending attunement ends the item's benefits, and picks made for them (its tool).
    remove_inapplicable_picks(db, character)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post(BASE + "/{row_id}/notes", response_class=HTMLResponse)
def notes(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    row_id: int,
    notes: Annotated[str, Form()] = "",
):
    _row(db, character, row_id).notes = notes.strip()[:255] or None
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.get(BASE + "/{row_id}/remove", response_class=HTMLResponse)
def remove_confirm(request: Request, db: DbSession, character: OwnedCharacter, row_id: int):
    """Asks before removing, in place of the row's buttons."""
    context = {"character": character, "row": _row(db, character, row_id)}
    return _item_partial(request, "remove_confirm", context)


@router.post(BASE + "/{row_id}/remove", response_class=HTMLResponse)
def remove(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, row_id: int
):
    db.delete(_row(db, character, row_id))
    db.flush()
    remove_inapplicable_picks(db, character)
    db.commit()
    return refresh_sheet(request, db, user, character)


class CoinForm(BaseModel):
    pp: str = ""
    gp: str = ""
    ep: str = ""
    sp: str = ""
    cp: str = ""


def _coins_block(request, db, character, amount="", coin="gp", error=None, status_code=200):
    """The coins line with its add/spend form, redrawn alone to show a mistake."""
    context = {
        "character": character,
        "coin_summary": coin_summary(coin_values(db, character)),
        "coin_labels": COINS,
        "coin_amount": amount,
        "coin_choice": coin,
        "coin_error": error,
    }
    return _item_partial(request, "coins_block", context, status_code=status_code)


@router.post(BASE + "/coins/change", response_class=HTMLResponse)
def change_coins(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    amount: Annotated[str, Form()] = "",
    coin: Annotated[str, Form()] = "gp",
    action: Annotated[str, Form()] = "",
):
    """Gain or spend some coins. Spending breaks larger coins when there aren't enough of
    the one paid with."""
    labels = dict(COINS)
    raw = amount.strip()
    if coin not in labels or action not in ("gain", "spend"):
        raise HTTPException(status_code=400)
    if not raw.isdigit() or not 1 <= int(raw) <= MAX_COINS:
        error = "Enter how many coins, e.g. 15."
        return _coins_block(request, db, character, amount, coin, error, status_code=400)
    current = coin_values(db, character)
    if action == "gain":
        new = gain(current, coin, int(raw))
        if new[coin] > MAX_COINS:
            error = f"That's more than {MAX_COINS:,} {labels[coin].lower()}."
            return _coins_block(request, db, character, amount, coin, error, status_code=400)
    else:
        new = spend(current, coin, int(raw))
        if new is None:
            error = f"You don't have {raw} {labels[coin].lower()}, even breaking larger coins."
            return _coins_block(request, db, character, amount, coin, error, status_code=400)
    set_coins(db, character, new)
    db.commit()
    return refresh_sheet(request, db, user, character)


def _coins_form(request, character, coins: dict, error: str | None = None, status_code=200):
    context = {"character": character, "coins": coins, "coin_labels": COINS, "error": error}
    return _item_partial(request, "coins_form", context, status_code=status_code)


@router.get(BASE + "/coins/edit", response_class=HTMLResponse)
def edit_coins(request: Request, db: DbSession, character: OwnedCharacter):
    return _coins_form(request, character, coin_values(db, character))


@router.post(BASE + "/coins", response_class=HTMLResponse)
def coins(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    form: Annotated[CoinForm, Form()],
):
    values = {}
    for column, label in COINS:
        raw = getattr(form, column).strip() or "0"
        if not raw.isdigit() or int(raw) > MAX_COINS:
            error = f"{label} is a whole number from 0 to {MAX_COINS:,}."
            typed = {col: getattr(form, col) for col, _ in COINS}
            return _coins_form(request, character, typed, error, status_code=400)
        values[column] = int(raw)
    set_coins(db, character, values)
    db.commit()
    return refresh_sheet(request, db, user, character)

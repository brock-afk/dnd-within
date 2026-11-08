from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.content.queries import picked_row
from app.core.forms import parse_amount
from app.features.service import remove_inapplicable_picks
from app.inventory.form import CoinChangeForm, CoinForm
from app.inventory.models import CharacterItem, Item
from app.inventory.queries import HealingUse, coin_values, inventory, scroll_spells_query
from app.inventory.rules import MAX_ATTUNED, MAX_COINS, Coin, CoinChange, ItemCategory, gain, spend
from app.sheet import rules as sheet_rules
from app.sheet.queries import active_ac_spell_ids, max_hp
from app.sheet.service import apply_ac_spell, play_state
from app.spells.models import Spell


def _stack(db: Session, character: Character, item_id: int, quantity: int, spell_id=None) -> None:
    row = db.scalar(
        select(CharacterItem).where(
            CharacterItem.character_id == character.id,
            CharacterItem.item_id == item_id,
            CharacterItem.spell_id.is_(None)
            if spell_id is None
            else CharacterItem.spell_id == spell_id,
        )
    )
    if row is None:
        db.add(
            CharacterItem(
                character_id=character.id, item_id=item_id, spell_id=spell_id, quantity=quantity
            )
        )
    else:
        row.quantity += quantity


def add_item(
    db: Session, character: Character, item: Item, quantity: int, spell: Spell | None = None
) -> str | None:
    if item.category == ItemCategory.SCROLL:
        if spell is None:
            return "Choose the spell on the scroll."
        if spell.level != item.spell_level:
            return f"A {item.name} holds a spell of that level."
        _stack(db, character, item.id, quantity, spell.id)
    elif item.contents:
        for content in item.contents:
            _stack(db, character, content["item_id"], content["quantity"] * quantity)
    else:
        _stack(db, character, item.id, quantity)
    db.flush()
    return None


def add_from_catalog(
    db: Session, character: Character, item: Item, quantity: str, spell_id: str
) -> str | None:
    amount = parse_amount(quantity, 1, 999)
    if amount is None:
        return "Quantity is 1 to 999."
    spell = picked_row(db, Spell, scroll_spells_query(item, character.user_id), spell_id)
    return add_item(db, character, item, amount, spell)


def change_quantity(db: Session, row: CharacterItem, delta: str) -> str | None:
    if delta not in ("1", "-1"):
        return "Use − or + to change the quantity."
    row.quantity = max(1, row.quantity + int(delta))
    db.flush()
    return None


def use_item(db: Session, row: CharacterItem) -> str | None:
    if not row.item.consumable:
        return f"{row.name} isn't used up."
    use_one(db, row)
    return None


def use_one(db: Session, row: CharacterItem) -> None:
    row.quantity -= 1
    if row.quantity <= 0:
        db.delete(row)
    db.flush()


class HealOutcome(NamedTuple):
    error: str | None
    notice: str | None


def heal_with(db: Session, character: Character, use: HealingUse) -> HealOutcome:
    maximum = max_hp(db, character)
    if maximum is None:
        return HealOutcome("Set ability scores first: healing needs your max HP.", None)
    row, name = use.row, use.row.name
    amount, rolled = sheet_rules.roll_detail(use.dice)
    state = play_state(db, character)
    if use.temporary:
        if amount > state.temp_hp:
            sheet_rules.set_temp_hp(state, amount, row.spell.name)
            notice = f"{name}: {amount} temporary hit points ({rolled})."
        else:
            notice = f"{name}: rolled {amount} ({rolled}); you kept your {state.temp_hp} temp HP."
    else:
        before = sheet_rules.current_hp(state, maximum)
        sheet_rules.heal(state, amount, maximum)
        gained = sheet_rules.current_hp(state, maximum) - before
        notice = f"{name}: healed {gained} ({rolled})" + (
            f", {amount - gained} over your max." if gained < amount else "."
        )
    use_one(db, row)
    return HealOutcome(None, notice)


def cast_ac_scroll(db: Session, character: Character, row: CharacterItem) -> str | None:
    if row.spell_id in active_ac_spell_ids(db, character):
        return f"{row.spell.name} is already on."
    apply_ac_spell(db, character, row.spell)
    use_one(db, row)
    return None


def attune(db: Session, character: Character, row: CharacterItem, attuned: str) -> str | None:
    if not row.item.requires_attunement:
        return f"{row.name} doesn't need attunement."
    wanted = attuned == "1"
    if wanted and not row.attuned:
        count = sum(1 for r in inventory(db, character) if r.attuned)
        if count >= MAX_ATTUNED:
            return f"You can be attuned to at most {MAX_ATTUNED} items. End one first."
    row.attuned = wanted
    db.flush()
    remove_inapplicable_picks(db, character)
    return None


def set_notes(db: Session, row: CharacterItem, notes: str) -> None:
    row.notes = notes.strip()[:255] or None
    db.flush()


def remove_item(db: Session, character: Character, row: CharacterItem) -> None:
    db.delete(row)
    db.flush()
    remove_inapplicable_picks(db, character)


def set_coins(db: Session, character: Character, values: dict[str, int]) -> None:
    state = play_state(db, character)
    for column, amount in values.items():
        setattr(state, column, amount)
    db.flush()


def change_coins(db: Session, character: Character, form: CoinChangeForm) -> str | None:
    if form.coin not in Coin or form.action not in CoinChange:
        return "Choose a coin, then Add or Spend."
    amount = form.count()
    if amount is None:
        return "Enter how many coins, e.g. 15."
    coin = Coin(form.coin)
    current = coin_values(db, character)
    if form.action == CoinChange.ADD:
        new = gain(current, coin, amount)
        if new[coin] > MAX_COINS:
            return f"That's more than {MAX_COINS:,} {coin.noun}."
    else:
        new = spend(current, coin, amount)
        if new is None:
            return f"You don't have {amount:,} {coin.noun}, even breaking larger coins."
    set_coins(db, character, new)
    return None


def save_coins(db: Session, character: Character, form: CoinForm) -> str | None:
    values = form.values()
    for coin in Coin:
        if values[coin] is None:
            return f"{coin.label} is a whole number from 0 to {MAX_COINS:,}."
    set_coins(db, character, values)
    return None

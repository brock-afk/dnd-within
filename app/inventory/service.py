"""What a character carries: adding (packs expand, scrolls hold a spell), quantities, using
consumables, attunement and coins. Changes are flushed but not committed; routes commit."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.inventory.models import CharacterItem, Item
from app.inventory.queries import MAX_ATTUNED, inventory
from app.sheet.service import play_state
from app.spells.models import Spell


def _stack(db: Session, character: Character, item_id: int, quantity: int, spell_id=None) -> None:
    """Add to the row for this item (and spell), or start one."""
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
    """Add `quantity` of an item. A pack adds its contents instead; a scroll needs the spell
    it holds. Returns an error message instead if that can't be done."""
    if item.category == "scroll":
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


def change_quantity(db: Session, row: CharacterItem, delta: int) -> None:
    """Add or take away, but never below 1: getting rid of an item is Remove (which asks
    first), so a stray click can't lose the only backpack."""
    row.quantity = max(1, row.quantity + delta)
    db.flush()


def use_one(db: Session, row: CharacterItem) -> None:
    """Spend one of a consumable; the last one used is gone."""
    row.quantity -= 1
    if row.quantity <= 0:
        db.delete(row)
    db.flush()


def set_attuned(db: Session, character: Character, row: CharacterItem, attuned: bool) -> str | None:
    if not row.item.requires_attunement:
        return f"{row.name} doesn't need attunement."
    if attuned and not row.attuned:
        count = sum(1 for r in inventory(db, character) if r.attuned)
        if count >= MAX_ATTUNED:
            return f"You can be attuned to at most {MAX_ATTUNED} items. End one first."
    row.attuned = attuned
    db.flush()
    return None


def set_coins(db: Session, character: Character, values: dict[str, int]) -> None:
    state = play_state(db, character)
    for column, amount in values.items():
        setattr(state, column, amount)
    db.flush()

"""What a character carries: adding (packs expand, scrolls hold a spell), quantities, using
consumables, attunement and coins. Changes are flushed but not committed; routes commit."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.content.queries import available, visible
from app.inventory.models import CharacterItem, Item
from app.sheet.models import CharacterPlayState
from app.sheet.service import play_state
from app.spells.models import Spell

MAX_ATTUNED = 3  # 2024 rules: at most three magic items at once
# Coins by their full names (not GP, SP...), highest first.
COINS = [("pp", "Platinum"), ("gp", "Gold"), ("ep", "Electrum"), ("sp", "Silver"), ("cp", "Copper")]
MAX_COINS = 1_000_000


def inventory(db: Session, character: Character) -> list[CharacterItem]:
    """Everything the character carries, by name."""
    rows = db.scalars(select(CharacterItem).where(CharacterItem.character_id == character.id))
    return sorted(rows, key=lambda row: row.name.lower())


def character_item(db: Session, character: Character, row_id: int) -> CharacterItem | None:
    row = db.get(CharacterItem, row_id)
    return row if row is not None and row.character_id == character.id else None


SEARCH_MIN_LENGTH = 2
SEARCH_LIMIT = 20


def price(cost_cp: int | None) -> str:
    """"40 gold", "5 silver", "2 copper", or "" without a price."""
    if cost_cp is None:
        return ""
    for coin, value in [("gold", 100), ("silver", 10)]:
        if cost_cp % value == 0:
            return f"{cost_cp // value} {coin}"
    return f"{cost_cp} copper"


def item_detail(item: Item) -> str:
    """"Common · 50 gold": rarity and price, whichever it has."""
    rarity = (item.rarity or "").replace("_", " ").capitalize()
    return " · ".join(part for part in [rarity, price(item.cost_cp)] if part)


def search_items(db: Session, query: str, user_id: int) -> list[Item]:
    """Catalog items named like `query`, once it's long enough: published ones and this
    user's homebrew."""
    query = query.strip()
    if len(query) < SEARCH_MIN_LENGTH:
        return []
    return list(
        db.scalars(
            select(Item)
            .where(
                available(Item),
                visible(Item, user_id),
                Item.name.contains(query, autoescape=True),
            )
            .order_by(Item.name)
            .limit(SEARCH_LIMIT)
        )
    )


def pack_contents(db: Session, item: Item) -> list[tuple[Item, int]]:
    """(item, quantity) a pack adds."""
    return [(db.get(Item, c["item_id"]), c["quantity"]) for c in item.contents or []]


def scroll_spells(db: Session, item: Item) -> list[Spell]:
    """Spells a scroll of this level can hold: any spell of that level."""
    return list(
        db.scalars(
            select(Spell)
            .where(Spell.level == item.spell_level, available(Spell))
            .order_by(Spell.name)
        )
    )


def _stack(db: Session, character: Character, item_id: int, quantity: int, spell_id=None) -> None:
    """Add to the row for this item (and spell), or start one."""
    row = db.scalar(
        select(CharacterItem).where(
            CharacterItem.character_id == character.id,
            CharacterItem.item_id == item_id,
            CharacterItem.spell_id.is_(None) if spell_id is None else CharacterItem.spell_id == spell_id,
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


def coins(db: Session, character: Character) -> CharacterPlayState | None:
    return db.get(CharacterPlayState, character.id)


def coin_summary(values: dict[str, int]) -> str:
    """"65 gold, 3 silver": the coins the character has, highest first; "" with none."""
    return ", ".join(
        f"{values[column]:,} {label.lower()}" for column, label in COINS if values[column]
    )


def coin_values(db: Session, character: Character) -> dict[str, int]:
    """{"pp": 0, "gp": 65, ...}, highest coin first."""
    state = coins(db, character)
    return {column: getattr(state, column) if state else 0 for column, _ in COINS}


def set_coins(db: Session, character: Character, values: dict[str, int]) -> None:
    state = play_state(db, character)
    for column, amount in values.items():
        setattr(state, column, amount)
    db.flush()


def digest(db: Session, character: Character, rows: list[CharacterItem]) -> str:
    """"65 gold · 12 items" for the collapsed Inventory section."""
    money = coin_summary(coin_values(db, character))
    count = f"{len(rows)} item{'s' if len(rows) != 1 else ''}" if rows else ""
    return " · ".join(part for part in [money, count] if part)

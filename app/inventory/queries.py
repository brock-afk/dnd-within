from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.content.queries import available, available_row, visible
from app.core.forms import parse_id
from app.features.models import Feature
from app.inventory.models import CharacterItem, Item
from app.inventory.rules import COINS
from app.sheet.models import CharacterPlayState
from app.spells.models import Spell
from app.spells.queries import pickable_spells


def inventory(db: Session, character: Character) -> list[CharacterItem]:
    """Everything the character carries, by name."""
    rows = db.scalars(select(CharacterItem).where(CharacterItem.character_id == character.id))
    return sorted(rows, key=lambda row: row.name.lower())


def item_features(db: Session, rows: list[CharacterItem]) -> dict[int, list[Feature]]:
    """{item id: its features} for the items carried: what each item does, shown with it in
    the inventory whether or not it's attuned."""
    ids = {row.item_id for row in rows}
    features = db.scalars(
        select(Feature)
        .where(Feature.item_id.in_(ids), available(Feature))
        .order_by(Feature.position)
    )
    result: dict[int, list[Feature]] = {}
    for feature in features:
        result.setdefault(feature.item_id, []).append(feature)
    return result


@dataclass(frozen=True)
class HealingUse:
    """A carried item that heals from the HP panel: a potion (its own dice), or a scroll of a
    healing spell (the spell's dice; False Life's are temporary hit points)."""

    row: CharacterItem
    dice: str
    temporary: bool = False

    @property
    def verb(self) -> str:
        return "Cast" if self.row.spell else "Drink" if self.row.item.consumable else "Use"


def healing_uses(rows: list[CharacterItem]) -> list[HealingUse]:
    uses = []
    for row in rows:
        if row.item.healing:
            uses.append(HealingUse(row, row.item.healing))
        elif row.spell and (healing := row.spell.details.get("healing")):
            uses.append(HealingUse(row, healing["dice"], healing.get("temporary", False)))
    return uses


def is_ac_scroll(row: CharacterItem) -> bool:
    return bool(row.spell and row.spell.details.get("ac_effect"))


def ac_scrolls(rows: list[CharacterItem], active_spell_ids: set[int]) -> list[CharacterItem]:
    # Like the prepared spell, a scroll isn't offered while its effect is already on.
    return [row for row in rows if is_ac_scroll(row) and row.spell_id not in active_spell_ids]


SEARCH_MIN_LENGTH = 2
SEARCH_LIMIT = 20


def price(cost_cp: int | None) -> str:
    """ "40 gold", "5 silver", "2 copper", or "" without a price."""
    if cost_cp is None:
        return ""
    for coin, value in [("gold", 100), ("silver", 10)]:
        if cost_cp % value == 0:
            return f"{cost_cp // value} {coin}"
    return f"{cost_cp} copper"


def item_detail(item: Item) -> str:
    """ "Common · 50 gold": rarity and price, whichever it has."""
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


def catalog_item(db: Session, key: str, user_id: int) -> Item | None:
    return available_row(db, Item, parse_id(key), user_id=user_id)


@dataclass(frozen=True)
class ItemSearchView:
    query: str
    min_length: int
    results: list[tuple[Item, str]]


def item_search(db: Session, character: Character, query: str) -> ItemSearchView:
    return ItemSearchView(
        query=query,
        min_length=SEARCH_MIN_LENGTH,
        results=[(item, item_detail(item)) for item in search_items(db, query, character.user_id)],
    )


def pack_contents(db: Session, item: Item) -> list[tuple[Item, int]]:
    """(item, quantity) a pack adds."""
    return [(db.get(Item, c["item_id"]), c["quantity"]) for c in item.contents or []]


def scroll_spells(db: Session, item: Item, user_id: int) -> list[Spell]:
    """A Spell Scroll holds any spell of its level, whatever the class."""
    query = pickable_spells(user_id).where(Spell.level == item.spell_level)
    return list(db.scalars(query.order_by(Spell.name)))


@dataclass(frozen=True)
class AddConfirmView:
    item: Item
    detail: str
    contents: list[tuple[Item, int]]
    spells: list[Spell]
    query: str
    quantity: str
    spell_id: str


def add_confirmation(
    db: Session,
    character: Character,
    item: Item,
    query: str,
    quantity: str = "1",
    spell_id: str = "",
) -> AddConfirmView:
    return AddConfirmView(
        item=item,
        detail=item_detail(item),
        contents=pack_contents(db, item),
        spells=scroll_spells(db, item, character.user_id) if item.category == "scroll" else [],
        query=query,
        quantity=quantity,
        spell_id=spell_id,
    )


def coins(db: Session, character: Character) -> CharacterPlayState | None:
    return db.get(CharacterPlayState, character.id)


def coin_summary(values: dict[str, int]) -> str:
    """ "65 gold, 3 silver": the coins the character has, highest first; "" with none."""
    return ", ".join(
        f"{values[column]:,} {label.lower()}" for column, label in COINS if values[column]
    )


def coin_values(db: Session, character: Character) -> dict[str, int]:
    """{"pp": 0, "gp": 65, ...}, highest coin first."""
    state = coins(db, character)
    return {column: getattr(state, column) if state else 0 for column, _ in COINS}


def digest(db: Session, character: Character, rows: list[CharacterItem]) -> str:
    """ "65 gold · 12 items" for the collapsed Inventory section."""
    money = coin_summary(coin_values(db, character))
    count = f"{len(rows)} item{'s' if len(rows) != 1 else ''}" if rows else ""
    return " · ".join(part for part in [money, count] if part)


@dataclass(frozen=True)
class CoinsBlockView:
    coin_summary: str
    coin_amount: str
    coin_choice: str


def coins_block_view(
    db: Session, character: Character, amount: str = "", coin: str = "gp"
) -> CoinsBlockView:
    return CoinsBlockView(coin_summary(coin_values(db, character)), amount, coin)


@dataclass(frozen=True)
class CoinsFormView:
    coins: dict[str, int | str]


def coins_form_view(
    db: Session, character: Character, typed: dict[str, str] | None = None
) -> CoinsFormView:
    return CoinsFormView(coins=typed if typed is not None else coin_values(db, character))

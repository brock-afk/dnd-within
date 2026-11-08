from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.content.queries import available, available_row, visible
from app.core.forms import parse_id
from app.features.models import Feature
from app.inventory.models import CharacterItem, Item
from app.inventory.rules import Coin, ItemCategory
from app.sheet.models import CharacterPlayState
from app.spells.models import Spell
from app.spells.queries import pickable_spells


def inventory(db: Session, character: Character) -> list[CharacterItem]:
    rows = db.scalars(select(CharacterItem).where(CharacterItem.character_id == character.id))
    return sorted(rows, key=lambda row: row.name.lower())


def item_features(db: Session, rows: list[CharacterItem]) -> dict[int, list[Feature]]:
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
    return [row for row in rows if is_ac_scroll(row) and row.spell_id not in active_spell_ids]


SEARCH_MIN_LENGTH = 2
SEARCH_LIMIT = 20


def price(cost_cp: int | None) -> str:
    if cost_cp is None:
        return ""
    coin = next(c for c in (Coin.GOLD, Coin.SILVER, Coin.COPPER) if cost_cp % c.copper == 0)
    return f"{cost_cp // coin.copper} {coin.noun}"


def item_detail(item: Item) -> str:
    rarity = item.rarity.label if item.rarity else ""
    return " · ".join(part for part in [rarity, price(item.cost_cp)] if part)


def search_items(db: Session, query: str, user_id: int) -> list[Item]:
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
    return [(db.get(Item, c["item_id"]), c["quantity"]) for c in item.contents or []]


def scroll_spells_query(item: Item, user_id: int) -> Select[tuple[Spell]]:
    return pickable_spells(user_id).where(Spell.level == item.spell_level)


def scroll_spells(db: Session, item: Item, user_id: int) -> list[Spell]:
    return list(db.scalars(scroll_spells_query(item, user_id).order_by(Spell.name)))


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
        spells=scroll_spells(db, item, character.user_id)
        if item.category == ItemCategory.SCROLL
        else [],
        query=query,
        quantity=quantity,
        spell_id=spell_id,
    )


def coins(db: Session, character: Character) -> CharacterPlayState | None:
    return db.get(CharacterPlayState, character.id)


def coin_summary(values: dict[str, int]) -> str:
    return ", ".join(f"{values[coin]:,} {coin.noun}" for coin in Coin if values[coin])


def coin_values(db: Session, character: Character) -> dict[str, int]:
    state = coins(db, character)
    return {coin: getattr(state, coin) if state else 0 for coin in Coin}


def digest(db: Session, character: Character, rows: list[CharacterItem]) -> str:
    money = coin_summary(coin_values(db, character))
    count = f"{len(rows)} item{'s' if len(rows) != 1 else ''}" if rows else ""
    return " · ".join(part for part in [money, count] if part)


@dataclass(frozen=True)
class CoinsBlockView:
    coin_summary: str
    coin_amount: str
    coin_choice: str


def coins_block_view(
    db: Session, character: Character, amount: str = "", coin: str = Coin.GOLD
) -> CoinsBlockView:
    return CoinsBlockView(coin_summary(coin_values(db, character)), amount, coin)


@dataclass(frozen=True)
class CoinsFormView:
    coins: dict[str, int | str]


def coins_form_view(
    db: Session, character: Character, typed: dict[str, str] | None = None
) -> CoinsFormView:
    return CoinsFormView(coins=typed if typed is not None else coin_values(db, character))

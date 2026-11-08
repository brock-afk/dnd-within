from typing import Annotated

from fastapi import Depends, Form, HTTPException

from app.characters.dependencies import OwnedCharacter, owned_child
from app.core.db import DbSession
from app.inventory.models import CharacterItem, Item
from app.inventory.queries import HealingUse, catalog_item, healing_uses, is_ac_scroll


def get_item_row(row_id: int, db: DbSession, character: OwnedCharacter) -> CharacterItem:
    return owned_child(db, CharacterItem, row_id, character)


OwnedItemRow = Annotated[CharacterItem, Depends(get_item_row)]


def get_healing_item(row: OwnedItemRow) -> HealingUse:
    uses = healing_uses([row])
    if not uses:
        raise HTTPException(status_code=404)
    return uses[0]


def get_ac_scroll(row: OwnedItemRow) -> CharacterItem:
    if not is_ac_scroll(row):
        raise HTTPException(status_code=404)
    return row


HealingItem = Annotated[HealingUse, Depends(get_healing_item)]
AcScroll = Annotated[CharacterItem, Depends(get_ac_scroll)]


def _catalog_or_404(db: DbSession, character: OwnedCharacter, key: str) -> Item:
    item = catalog_item(db, key, character.user_id)
    if item is None:
        raise HTTPException(status_code=404)
    return item


def get_catalog_item(db: DbSession, character: OwnedCharacter, item: str = "") -> Item:
    return _catalog_or_404(db, character, item)


def get_posted_catalog_item(
    db: DbSession, character: OwnedCharacter, item_id: Annotated[str, Form()] = ""
) -> Item:
    return _catalog_or_404(db, character, item_id)


CatalogItem = Annotated[Item, Depends(get_catalog_item)]
PostedCatalogItem = Annotated[Item, Depends(get_posted_catalog_item)]

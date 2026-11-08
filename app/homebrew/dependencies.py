from typing import Annotated

from fastapi import Depends, HTTPException

from app.auth.dependencies import CurrentUser
from app.content.models import Source
from app.core.db import DbSession
from app.inventory.models import Item


def get_owned_item(item_id: int, db: DbSession, user: CurrentUser) -> Item:
    item = db.get(Item, item_id)
    if item is None or item.retired_at is not None:
        raise HTTPException(status_code=404)
    if db.get(Source, item.source_id).owner_user_id != user.id:
        raise HTTPException(status_code=404)
    return item


OwnedHomebrewItem = Annotated[Item, Depends(get_owned_item)]

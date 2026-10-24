"""A user's homebrew library: their own content source, holding items made in the editor.

Homebrew rows are ordinary content rows (items, features, choices) in a source owned by the
user, so everything that reads content works on them unchanged; only `visible()` keeps them
private. They're written through the same FeatureSync as content packs.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.characters.models import Character
from app.content.importer import FeatureSync
from app.content.loader import split_ref
from app.content.models import Source
from app.content.schema import ItemDef
from app.homebrew.form import ItemForm, build_item_def
from app.inventory.models import Item
from app.inventory.service import add_item


def homebrew_source(db: Session, user: User) -> Source:
    """The user's homebrew source, created the first time they make something."""
    slug = f"homebrew-{user.id}"
    source = db.scalar(select(Source).where(Source.slug == slug))
    if source is None:
        source = Source(
            slug=slug, name=f"{user.username}'s homebrew", kind="homebrew", owner_user_id=user.id
        )
        db.add(source)
        db.flush()
    return source


class HomebrewSync(FeatureSync):
    """Homebrew always names references with their source ("phb-2024/disguise-self"), so they
    resolve straight from the database rather than through a pack's `requires`."""

    def _id(self, model, ref: str, kind: str) -> int:
        source_slug, slug = split_ref(ref)
        row = self.db.scalar(
            select(model.id)
            .join(Source, Source.id == model.source_id)
            .where(Source.slug == source_slug, model.slug == slug)
        )
        if row is None:
            raise LookupError(f"{ref!r} isn't in the database")
        return row


def _unique_slug(db: Session, source: Source, slug: str, item: Item | None) -> str:
    taken = set(
        db.scalars(
            select(Item.slug).where(
                Item.source_id == source.id, Item.id != (item.id if item else 0)
            )
        )
    )
    candidate, n = slug, 2
    while candidate in taken:
        candidate = f"{slug[:46]}-{n}"
        n += 1
    return candidate


def save_item(
    db: Session, user: User, item_def: ItemDef, definition: dict, item: Item | None = None
) -> Item:
    """Create or update a homebrew item and its features. Doesn't commit."""
    source = homebrew_source(db, user)
    if item is None:
        item = Item(source_id=source.id, slug=_unique_slug(db, source, item_def.slug, None))
        db.add(item)
    item.name = item_def.name
    item.category = item_def.category
    item.rarity = item_def.rarity
    item.summary = item_def.summary
    item.description = item_def.description
    item.consumable = item_def.consumable
    item.requires_attunement = item_def.requires_attunement
    item.spell_level = None
    item.healing = item_def.healing
    item.contents = None
    item.definition = definition
    item.retired_at = None
    db.flush()
    HomebrewSync(db)._sync_features("item_id", item.id, item_def.features)
    db.flush()
    return item


def save_from_form(
    db: Session, user: User, form: ItemForm, item: Item | None, character: Character | None
) -> dict[str, str]:
    """Save the editor's item (a new one when `item` is None) and, when the editor was opened
    from `character`'s Add item, add one to their inventory. Returns {field: problem} instead,
    with nothing saved, when the form isn't valid."""
    item_def, errors = build_item_def(db, form)
    if errors:
        return errors
    saved = save_item(db, user, item_def, form.definition(), item)
    if character is not None:
        add_item(db, character, saved, 1)
    return {}


def delete_item(db: Session, item: Item) -> None:
    """Retire it: it leaves the library and Add item search, but characters carrying it keep
    it, benefits and all (its features stay active). Doesn't commit."""
    item.retired_at = datetime.now()
    db.flush()

"""View models for the homebrew pages: what each page shows, loaded from the database.
Rendering them is app/homebrew/page.py's job."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.characters.models import Character
from app.content.models import Source
from app.core.forms import parse_id
from app.homebrew.form import ItemForm
from app.inventory.models import Item
from app.inventory.queries import item_detail
from app.spells.models import Spell
from app.spells.queries import pickable_spells


def user_items(db: Session, user: User) -> list[Item]:
    """The user's homebrew items that haven't been deleted, by name."""
    return list(
        db.scalars(
            select(Item)
            .join(Source, Source.id == Item.source_id)
            .where(Source.owner_user_id == user.id, Item.retired_at.is_(None))
            .order_by(Item.name)
        )
    )


def opened_from(db: Session, user: User, key: str) -> Character | None:
    """The character whose Add item opened the editor, if it's the user's."""
    character_id = parse_id(key)
    character = db.get(Character, character_id) if character_id is not None else None
    return character if character is not None and character.user_id == user.id else None


@dataclass(frozen=True)
class LibraryView:
    user: User
    items: list[tuple[Item, str]]  # (item, its rarity and price)


def library_view(db: Session, user: User) -> LibraryView:
    return LibraryView(user=user, items=[(i, item_detail(i)) for i in user_items(db, user)])


@dataclass(frozen=True)
class EditorView:
    """The item editor: the form as typed, the item being edited (None for a new one), the
    character it was opened from, and the spells an item can grant."""

    user: User
    form: ItemForm
    item: Item | None
    character: Character | None
    spells: list[Spell]


def editor_view(db: Session, user: User, form: ItemForm, item: Item | None) -> EditorView:
    spells = db.scalars(pickable_spells(user.id).order_by(Spell.level, Spell.name)).all()
    return EditorView(
        user=user,
        form=form,
        item=item,
        character=opened_from(db, user, form.character),
        spells=list(spells),
    )


def new_item_view(db: Session, user: User, character_key: str) -> EditorView:
    """A blank editor. A character that isn't the user's is dropped, not kept in the form."""
    keep = opened_from(db, user, character_key) is not None
    return editor_view(db, user, ItemForm(character=character_key if keep else ""), None)


def edit_item_view(db: Session, user: User, item: Item) -> EditorView:
    """The editor filled from what was saved."""
    return editor_view(db, user, ItemForm(**(item.definition or {})).upgrade(), item)

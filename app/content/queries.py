"""Query helpers shared by everything that lists content."""

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.content.models import Source


def available(model) -> ColumnElement[bool]:
    """Rows that can be newly picked: not retired from their pack. Characters keep rows they
    already have, so only use this when offering options.

    Visibility settings for homebrew will narrow this too, so every list of pickable content
    should go through here."""
    return model.retired_at.is_(None)


def visible(model, user_id: int) -> ColumnElement[bool]:
    """Rows from published packs, plus this user's own homebrew. Other users' homebrew is
    private."""
    sources = select(Source.id).where(
        or_(Source.owner_user_id.is_(None), Source.owner_user_id == user_id)
    )
    return model.source_id.in_(sources)


def available_row(db: Session, model, row_id: int | None, user_id: int | None = None):
    """The row with this id if it can be picked, else None."""
    if row_id is None:
        return None
    where = [model.id == row_id, available(model)]
    if user_id is not None:
        where.append(visible(model, user_id))
    return db.scalar(select(model).where(*where))


def available_by_name(db: Session, model) -> list:
    """Every available row of `model`, by name: the options for picking one."""
    return list(db.scalars(select(model).where(available(model)).order_by(model.name)))

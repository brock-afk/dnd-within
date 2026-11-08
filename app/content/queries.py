from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.orm import Session

from app.content.models import Source
from app.core.forms import parse_id


def available(model) -> ColumnElement[bool]:
    return model.retired_at.is_(None)


def visible(model, user_id: int) -> ColumnElement[bool]:
    sources = select(Source.id).where(
        or_(Source.owner_user_id.is_(None), Source.owner_user_id == user_id)
    )
    return model.source_id.in_(sources)


def available_row(db: Session, model, row_id: int | None, user_id: int | None = None):
    if row_id is None:
        return None
    where = [model.id == row_id, available(model)]
    if user_id is not None:
        where.append(visible(model, user_id))
    return db.scalar(select(model).where(*where))


def picked_row(db: Session, model, query: Select, key: str):
    row_id = parse_id(key)
    if row_id is None:
        return None
    return db.scalar(query.where(model.id == row_id))


def available_by_name(db: Session, model) -> list:
    return list(db.scalars(select(model).where(available(model)).order_by(model.name)))

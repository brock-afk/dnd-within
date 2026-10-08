from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import Base


def sync_reference_rows(db: Session, model: type[Base], rows: list[dict]) -> None:
    """Insert or update fixed lookup rows (classes, species, ...) keyed by slug.

    Rows removed from `rows` are left in place, since characters may still reference them.
    """
    existing = {obj.slug: obj for obj in db.scalars(select(model))}
    for row in rows:
        obj = existing.get(row["slug"])
        if obj is None:
            db.add(model(**row))
        else:
            for key, value in row.items():
                setattr(obj, key, value)
    db.commit()

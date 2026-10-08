from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import CharacterClass, Subclass


def sync_subclasses(db: Session, subclasses_by_class: dict[str, list[dict]]) -> None:
    """Insert or update subclasses, keyed by (class slug, subclass slug). Never deletes."""
    classes = {c.slug: c for c in db.scalars(select(CharacterClass))}
    existing = {(s.class_id, s.slug): s for s in db.scalars(select(Subclass))}
    for class_slug, rows in subclasses_by_class.items():
        class_id = classes[class_slug].id
        for row in rows:
            subclass = existing.get((class_id, row["slug"]))
            if subclass is None:
                subclass = Subclass(class_id=class_id, slug=row["slug"])
                db.add(subclass)
            subclass.name = row["name"]
            subclass.summary = row["summary"]
    db.commit()


def subclass_ids(db: Session) -> dict[tuple[str, str], int]:
    """(class slug, subclass slug) -> subclass id, for syncing subclass features."""
    rows = db.execute(
        select(CharacterClass.slug, Subclass.slug, Subclass.id).join(
            Subclass, Subclass.class_id == CharacterClass.id
        )
    )
    return {(class_slug, slug): id_ for class_slug, slug, id_ in rows}

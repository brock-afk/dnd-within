from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import CharacterClass
from app.core.reference_data import sync_reference_rows
from app.spells.models import Spell


def sync_spells(db: Session, spells: list[dict]) -> None:
    """Sync spell rows, then each spell's class list (which `sync_reference_rows` can't do)."""
    sync_reference_rows(db, Spell, [{k: v for k, v in s.items() if k != "classes"} for s in spells])

    classes = {c.slug: c for c in db.scalars(select(CharacterClass))}
    by_slug = {s.slug: s for s in db.scalars(select(Spell))}
    for row in spells:
        by_slug[row["slug"]].classes = [classes[slug] for slug in row["classes"]]
    db.commit()

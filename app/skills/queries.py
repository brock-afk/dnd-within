from sqlalchemy import select
from sqlalchemy.orm import Session

from app.skills.models import CharacterSkill


def character_skills(db: Session, character_id: int) -> list[CharacterSkill]:
    rows = db.scalars(select(CharacterSkill).where(CharacterSkill.character_id == character_id))
    return sorted(rows, key=lambda cs: cs.skill.name)

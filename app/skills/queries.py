from sqlalchemy import select
from sqlalchemy.orm import Session

from app.skills.models import CharacterSkill, CharacterSkillExpertise


def character_skills(db: Session, character_id: int) -> list[CharacterSkill]:
    rows = db.scalars(select(CharacterSkill).where(CharacterSkill.character_id == character_id))
    return sorted(rows, key=lambda cs: cs.skill.name)


def expertise_skill_ids(db: Session, character_id: int) -> set[int]:
    query = select(CharacterSkillExpertise.skill_id).where(
        CharacterSkillExpertise.character_id == character_id
    )
    return set(db.scalars(query))

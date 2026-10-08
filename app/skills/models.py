from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.content.models import ContentMixin
from app.core.db import Base


class Skill(ContentMixin, Base):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("source_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    ability: Mapped[str] = mapped_column(String(3))  # "STR", "DEX", "CON", "INT", "WIS", "CHA"


class CharacterSkill(Base):
    """A skill a character is proficient in, and the choice that granted it."""

    __tablename__ = "character_skills"
    __table_args__ = (UniqueConstraint("character_id", "skill_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id"))
    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choices.id"))

    skill: Mapped[Skill] = relationship(lazy="joined")

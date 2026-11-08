from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.classes.models import CharacterClass
from app.core.db import Base


class CharacterLevel(Base):
    __tablename__ = "character_levels"
    __table_args__ = (
        UniqueConstraint("character_id", "character_level"),
        CheckConstraint("character_level BETWEEN 1 AND 20", name="character_level_range"),
        CheckConstraint("hp_method IN ('max', 'fixed', 'rolled')", name="hp_method_values"),
        CheckConstraint(
            "(hp_method = 'rolled') = (hp_roll IS NOT NULL)", name="hp_roll_iff_rolled"
        ),
        CheckConstraint("(character_level = 1) = (hp_method = 'max')", name="max_iff_first_level"),
        CheckConstraint("hp_roll >= 1", name="hp_roll_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    character_level: Mapped[int] = mapped_column(SmallInteger)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    hp_method: Mapped[str] = mapped_column(String(10))
    hp_roll: Mapped[int | None] = mapped_column(SmallInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    character_class: Mapped[CharacterClass] = relationship(lazy="joined")

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CharacterClass(Base):
    """A class definition, like Wizard."""

    __tablename__ = "classes"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(255))


class CharacterClassLevel(Base):
    """One class a character has, and their level in it ("Wizard 3").

    A multiclassed character has several rows. `position` 0 is the starting class, which
    matters because only it grants the class's full starting proficiencies.
    """

    __tablename__ = "character_classes"
    __table_args__ = (
        UniqueConstraint("character_id", "class_id"),
        UniqueConstraint("character_id", "position"),
        CheckConstraint("level BETWEEN 1 AND 20", name="level_range"),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    level: Mapped[int] = mapped_column(default=1)
    position: Mapped[int] = mapped_column(default=0)

    character_class: Mapped[CharacterClass] = relationship(lazy="joined")

    @property
    def is_starting_class(self) -> bool:
        return self.position == 0

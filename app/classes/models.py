from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class CharacterClass(Base):
    """A class definition, like Wizard."""

    __tablename__ = "classes"
    __table_args__ = (CheckConstraint("hit_die IN (6, 8, 10, 12)", name="hit_die_values"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(255))
    hit_die: Mapped[int] = mapped_column(SmallInteger, default=8, server_default="8")


class CharacterClassLevel(Base):
    """One class a character has ("Wizard 3").

    A multiclassed character has several rows. `position` 0 is the starting class, which
    matters because only it grants the class's full starting proficiencies. The class's level
    isn't stored here: it's the number of levels in the character's level history
    (app/leveling) that went to this class.
    """

    __tablename__ = "character_classes"
    __table_args__ = (
        UniqueConstraint("character_id", "class_id"),
        UniqueConstraint("character_id", "position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    position: Mapped[int] = mapped_column(default=0)

    character_class: Mapped[CharacterClass] = relationship(lazy="joined")
    character: Mapped["Character"] = relationship(back_populates="classes")  # noqa: F821

    @property
    def level(self) -> int:
        return self.character.class_level(self.class_id)

    @property
    def is_starting_class(self) -> bool:
        return self.position == 0

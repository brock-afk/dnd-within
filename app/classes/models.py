from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.content.models import ContentMixin
from app.core.db import Base


class CharacterClass(ContentMixin, Base):
    """A class definition, like Wizard."""

    __tablename__ = "classes"
    __table_args__ = (
        UniqueConstraint("source_id", "slug"),
        CheckConstraint("hit_die IN (6, 8, 10, 12)", name="hit_die_values"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(255))
    hit_die: Mapped[int] = mapped_column(SmallInteger, default=8, server_default="8")
    # Saving throw proficiencies, e.g. ["INT", "WIS"]; only the starting class grants them.
    saving_throws: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default=text("(json_array())")
    )
    # {"ability": "INT", "prepared": [20 counts]} for spellcasting classes, else NULL.
    spellcasting: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class Subclass(ContentMixin, Base):
    """A subclass of one class, like the Wizard's Evoker. Its source can differ from its
    class's: a third-party book can add a subclass to a PHB class."""

    __tablename__ = "subclasses"
    __table_args__ = (
        # class_id first: this index also serves the class_id foreign key.
        UniqueConstraint("class_id", "source_id", "slug"),
        # Lets character_classes point at (subclass, class) together, so the database can
        # check that a character's subclass belongs to that row's class.
        UniqueConstraint("id", "class_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(255))


class CharacterClassLevel(Base):
    """One class a character has ("Wizard 3 (Evoker)").

    A multiclassed character has several rows. `position` 0 is the starting class, which
    matters because only it grants the class's full starting proficiencies. The class's level
    isn't stored here: it's the number of levels in the character's level history
    (app/leveling) that went to this class.

    The subclass lives here, not on the character: each class a character has gets its own
    subclass slot, and the composite foreign key makes sure the subclass is one of this
    row's class.
    """

    __tablename__ = "character_classes"
    __table_args__ = (
        UniqueConstraint("character_id", "class_id"),
        UniqueConstraint("character_id", "position"),
        CheckConstraint("position >= 0", name="position_non_negative"),
        ForeignKeyConstraint(
            ["subclass_id", "class_id"],
            ["subclasses.id", "subclasses.class_id"],
            name="fk_character_classes_subclass_id_class_id_subclasses",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    # NULL until the class reaches its subclass level. Its foreign key is the composite one above.
    subclass_id: Mapped[int | None] = mapped_column()
    position: Mapped[int] = mapped_column(default=0)

    character_class: Mapped[CharacterClass] = relationship(lazy="joined")
    subclass: Mapped[Subclass | None] = relationship(
        lazy="joined", foreign_keys=[subclass_id], viewonly=True
    )
    character: Mapped[Character] = relationship(back_populates="classes")  # noqa: F821

    @property
    def level(self) -> int:
        return self.character.class_level(self.class_id)

    @property
    def is_starting_class(self) -> bool:
        return self.position == 0

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
from app.core.db import Base, NullableJSON


class CharacterClass(ContentMixin, Base):
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
    saving_throws: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default=text("(json_array())")
    )
    spellcasting: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)


class Subclass(ContentMixin, Base):
    __tablename__ = "subclasses"
    __table_args__ = (
        UniqueConstraint("class_id", "source_id", "slug"),
        UniqueConstraint("id", "class_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(255))


class CharacterClassLevel(Base):
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

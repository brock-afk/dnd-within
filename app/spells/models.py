from sqlalchemy import Column, ForeignKey, String, Table, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.classes.models import CharacterClass
from app.core.db import Base

# Which classes have a spell on their spell list.
class_spells = Table(
    "class_spells",
    Base.metadata,
    Column("class_id", ForeignKey("classes.id"), primary_key=True),
    Column("spell_id", ForeignKey("spells.id"), primary_key=True),
)


class Spell(Base):
    __tablename__ = "spells"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    level: Mapped[int]  # 0 = cantrip
    school: Mapped[str] = mapped_column(String(20))
    casting_time: Mapped[str] = mapped_column(String(40))
    range: Mapped[str] = mapped_column(String(40))
    components: Mapped[str] = mapped_column(String(20))
    duration: Mapped[str] = mapped_column(String(40))
    concentration: Mapped[bool] = mapped_column(default=False)
    ritual: Mapped[bool] = mapped_column(default=False)
    summary: Mapped[str] = mapped_column(String(255))

    classes: Mapped[list[CharacterClass]] = relationship(secondary=class_spells)

    @property
    def detail(self) -> str:
        """One-line stat summary, e.g. "Evocation · Action · 120 ft · Concentration"."""
        parts = [self.school, self.casting_time, self.range]
        if self.ritual:
            parts.append("Ritual")
        if self.concentration:
            parts.append("Concentration")
        return " · ".join(parts)


class CharacterSpell(Base):
    """A spell a character knows (a cantrip, or a spell in a spellbook), and the choice that granted it."""

    __tablename__ = "character_spells"
    __table_args__ = (UniqueConstraint("character_id", "spell_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id"))
    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choices.id"))

    spell: Mapped[Spell] = relationship(lazy="joined")

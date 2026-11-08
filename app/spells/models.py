from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    ForeignKey,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.classes.models import CharacterClass
from app.content.models import ContentMixin
from app.core.db import Base, enum_column
from app.spells.rules import AcquiredVia, CastingUnit, RangeKind, School

class_spells = Table(
    "class_spells",
    Base.metadata,
    Column("class_id", ForeignKey("classes.id"), primary_key=True),
    Column("spell_id", ForeignKey("spells.id"), primary_key=True),
)


class Spell(ContentMixin, Base):
    __tablename__ = "spells"
    __table_args__ = (
        UniqueConstraint("source_id", "slug"),
        CheckConstraint("level BETWEEN 0 AND 9", name="level_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(80))
    level: Mapped[int]
    school: Mapped[School] = mapped_column(enum_column(School, 20, check="school_values"))
    casting_unit: Mapped[CastingUnit] = mapped_column(
        enum_column(CastingUnit, 20, check="casting_unit_values")
    )
    concentration: Mapped[bool] = mapped_column(default=False)
    ritual: Mapped[bool] = mapped_column(default=False)
    summary: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    classes: Mapped[list[CharacterClass]] = relationship(secondary=class_spells)

    @property
    def stat_line(self) -> str:
        amount = self.details.get("casting_time", {}).get("amount", 1)
        parts = [self.school.label, _casting_label(self.casting_unit, amount)]
        parts.append(_range_label(self.details.get("range", {}), self.details.get("area")))
        return " · ".join(p for p in parts if p)

    @property
    def detail(self) -> str:
        parts = [self.stat_line]
        if self.ritual:
            parts.append("Ritual")
        if self.concentration:
            parts.append("Concentration")
        return " · ".join(parts)


def _casting_label(unit: CastingUnit, amount: int) -> str:
    if action := unit.action:
        return action.label
    return f"{amount} {unit}{'s' if amount != 1 else ''}"


def _range_label(rng: dict, area: dict | None) -> str:
    kind = rng.get("kind")
    if kind == RangeKind.DISTANCE:
        label = f"{rng['feet']} ft" if rng.get("feet") else f"{rng.get('miles')} miles"
    else:
        label = RangeKind(kind).label if kind in RangeKind else ""
    if area and kind == RangeKind.SELF:
        label += f" ({area['feet']}-ft {area['shape']})"
    return label


class CharacterSpell(Base):
    __tablename__ = "character_spells"
    __table_args__ = (UniqueConstraint("character_id", "spell_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id"))
    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choices.id"))

    spell: Mapped[Spell] = relationship(lazy="joined")


class SpellbookEntry(Base):
    __tablename__ = "spellbook_entries"
    __table_args__ = (UniqueConstraint("character_id", "spell_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id"))
    acquired_via: Mapped[AcquiredVia] = mapped_column(
        enum_column(AcquiredVia, 20, check="acquired_via_values")
    )
    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choices.id"))
    source_note: Mapped[str | None] = mapped_column(String(120))

    spell: Mapped[Spell] = relationship(lazy="joined")

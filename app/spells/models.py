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
from app.core.db import Base

# Which classes have a spell on their spell list.
class_spells = Table(
    "class_spells",
    Base.metadata,
    Column("class_id", ForeignKey("classes.id"), primary_key=True),
    Column("spell_id", ForeignKey("spells.id"), primary_key=True),
)


class Spell(ContentMixin, Base):
    """A spell. Fields used for filtering and sorting are columns; the rest of the structured
    rules (range, area, components, damage, scaling, ...) live in `details`, validated against
    app/content/schema.py:SpellDef when imported."""

    __tablename__ = "spells"
    __table_args__ = (
        UniqueConstraint("source_id", "slug"),
        CheckConstraint("level BETWEEN 0 AND 9", name="level_range"),
        CheckConstraint(
            "casting_unit IN ('action', 'bonus_action', 'reaction', 'minute', 'hour')",
            name="casting_unit_values",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(80))
    level: Mapped[int]  # 0 = cantrip
    school: Mapped[str] = mapped_column(String(20))
    casting_unit: Mapped[str] = mapped_column(String(20))
    concentration: Mapped[bool] = mapped_column(default=False)
    ritual: Mapped[bool] = mapped_column(default=False)
    summary: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)  # full text, private packs only
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    classes: Mapped[list[CharacterClass]] = relationship(secondary=class_spells)

    @property
    def stat_line(self) -> str:
        """School, casting time and range, e.g. "Evocation · Action · 120 ft"."""
        parts = [self.school.title(), _casting_label(self.details.get("casting_time", {}))]
        parts.append(_range_label(self.details.get("range", {}), self.details.get("area")))
        return " · ".join(p for p in parts if p)

    @property
    def detail(self) -> str:
        """The stat line plus ritual/concentration, e.g. "Evocation · Action · 120 ft ·
        Concentration". Spell lists show those two as tags instead (partials/spell_list.html)."""
        parts = [self.stat_line]
        if self.ritual:
            parts.append("Ritual")
        if self.concentration:
            parts.append("Concentration")
        return " · ".join(parts)


def _casting_label(casting: dict) -> str:
    unit, amount = casting.get("unit"), casting.get("amount", 1)
    if unit in ("minute", "hour"):
        return f"{amount} {unit}{'s' if amount != 1 else ''}"
    return {"action": "Action", "bonus_action": "Bonus Action", "reaction": "Reaction"}.get(
        unit, ""
    )


def _range_label(rng: dict, area: dict | None) -> str:
    kind = rng.get("kind")
    if kind == "distance":
        label = f"{rng['feet']} ft" if rng.get("feet") else f"{rng.get('miles')} miles"
    else:
        label = (kind or "").title()
    if area and kind == "self":
        label += f" ({area['feet']}-ft {area['shape']})"
    return label


class CharacterSpell(Base):
    """A spell a character knows (a cantrip, or a spell in a spellbook), and the choice that granted it."""

    __tablename__ = "character_spells"
    __table_args__ = (UniqueConstraint("character_id", "spell_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id"))
    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choices.id"))

    spell: Mapped[Spell] = relationship(lazy="joined")


class SpellbookEntry(Base):
    """A spell written in a character's spellbook, and how it got there.

    Separate from character_spells (cantrips and other known spells) because a spellbook has
    its own rules: spells are added on level up, by features, or copied from scrolls and other
    books, and only spells in the book can be prepared.
    """

    __tablename__ = "spellbook_entries"
    __table_args__ = (
        UniqueConstraint("character_id", "spell_id"),  # a book can't hold a spell twice
        CheckConstraint(
            "acquired_via IN ('level_up', 'feature', 'copied')", name="acquired_via_values"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id"))
    acquired_via: Mapped[str] = mapped_column(String(20))
    # The level-up or feature choice that added it; NULL for copied spells.
    choice_id: Mapped[int | None] = mapped_column(ForeignKey("choices.id"))
    # Where a copied spell came from, e.g. "Scroll from the crypt". Optional.
    source_note: Mapped[str | None] = mapped_column(String(120))

    spell: Mapped[Spell] = relationship(lazy="joined")

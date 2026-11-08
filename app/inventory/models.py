from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.content.models import ContentMixin
from app.core.db import Base, NullableJSON
from app.spells.models import Spell

CATEGORIES = ("gear", "consumable", "pack", "scroll", "tool", "magic")
RARITIES = ("common", "uncommon", "rare", "very_rare", "legendary", "artifact")


class Item(ContentMixin, Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("source_id", "slug"),
        CheckConstraint(
            "category IN (" + ", ".join(f"'{c}'" for c in CATEGORIES) + ")",
            name="category_values",
        ),
        CheckConstraint(
            "rarity IS NULL OR rarity IN (" + ", ".join(f"'{r}'" for r in RARITIES) + ")",
            name="rarity_values",
        ),
        CheckConstraint(
            "(category = 'scroll') = (spell_level IS NOT NULL)", name="scrolls_have_spell_level"
        ),
        CheckConstraint("spell_level BETWEEN 0 AND 9", name="spell_level_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(20))
    rarity: Mapped[str | None] = mapped_column(String(20))
    cost_cp: Mapped[int | None] = mapped_column()
    weight_lb: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    summary: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    consumable: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    requires_attunement: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    spell_level: Mapped[int | None] = mapped_column(SmallInteger)
    healing: Mapped[str | None] = mapped_column(String(20))
    contents: Mapped[list[dict[str, Any]] | None] = mapped_column(NullableJSON)
    definition: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)


class CharacterItem(Base):
    __tablename__ = "character_items"
    __table_args__ = (CheckConstraint("quantity >= 1", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"))
    spell_id: Mapped[int | None] = mapped_column(ForeignKey("spells.id"))
    quantity: Mapped[int] = mapped_column(default=1)
    attuned: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    item: Mapped[Item] = relationship(lazy="joined")
    spell: Mapped[Spell | None] = relationship(lazy="joined")

    @property
    def name(self) -> str:
        return f"Spell Scroll: {self.spell.name}" if self.spell else self.item.name

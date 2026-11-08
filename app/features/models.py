from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, NullableJSON, enum_column, values_check
from app.features.rules import Action

SHEET_VALUES = "sheet IN ('senses', 'saves', 'speed', 'resistances', 'traits')"


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint(
            "(class_id IS NOT NULL) + (species_id IS NOT NULL) + (subclass_id IS NOT NULL)"
            " + (background_id IS NOT NULL) + (feat_id IS NOT NULL) + (item_id IS NOT NULL)"
            " + (option_id IS NOT NULL) = 1",
            name="one_source",
        ),
        CheckConstraint(
            "applies_to IN ('all', 'starting_class', 'multiclass')", name="applies_to_values"
        ),
        UniqueConstraint("class_id", "slug"),
        UniqueConstraint("species_id", "slug"),
        UniqueConstraint("subclass_id", "slug"),
        UniqueConstraint("background_id", "slug"),
        UniqueConstraint("feat_id", "slug"),
        UniqueConstraint("item_id", "slug"),
        UniqueConstraint("option_id", "slug"),
        values_check("action", Action, "action_values"),
        CheckConstraint(SHEET_VALUES, name="sheet_values"),
        CheckConstraint(
            "(spends_feature_id IS NULL) = (spends_amount IS NULL)", name="spends_together"
        ),
        CheckConstraint("spends_amount >= 1", name="spends_amount_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"))
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"))
    subclass_id: Mapped[int | None] = mapped_column(ForeignKey("subclasses.id"))
    background_id: Mapped[int | None] = mapped_column(ForeignKey("backgrounds.id"))
    feat_id: Mapped[int | None] = mapped_column(ForeignKey("feats.id"))
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"))
    option_id: Mapped[int | None] = mapped_column(ForeignKey("choice_options.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    level: Mapped[int] = mapped_column(default=1)
    applies_to: Mapped[str] = mapped_column(String(20), default="all", server_default="all")
    uses: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)
    slot_recovery: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)
    grants: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)
    action: Mapped[Action | None] = mapped_column(enum_column(Action, 20))
    when: Mapped[str | None] = mapped_column(String(120))
    sheet: Mapped[str | None] = mapped_column(String(20))
    spends_feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id"))
    spends_amount: Mapped[int | None] = mapped_column(SmallInteger)
    position: Mapped[int] = mapped_column(default=0)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)

    choices: Mapped[list[Choice]] = relationship(
        back_populates="feature", order_by="Choice.position", lazy="selectin"
    )
    spells: Mapped[list[FeatureSpell]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class FeatureSpell(Base):
    __tablename__ = "feature_spells"

    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), primary_key=True
    )
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id"), primary_key=True)
    free_cast: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    charge_cost: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    always_prepared: Mapped[bool] = mapped_column(default=True, server_default=text("1"))
    note: Mapped[str | None] = mapped_column(String(255))

    spell: Mapped[Spell] = relationship(lazy="joined")  # noqa: F821


class Choice(Base):
    __tablename__ = "choices"
    __table_args__ = (
        UniqueConstraint("feature_id", "slug"),
        CheckConstraint("level BETWEEN 1 AND 20", name="level_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    count: Mapped[int] = mapped_column(default=1)
    count_by_level: Mapped[list[int] | None] = mapped_column(NullableJSON)
    level: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    in_play: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    position: Mapped[int] = mapped_column(default=0)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)

    feature: Mapped[Feature] = relationship(back_populates="choices", lazy="joined")
    options: Mapped[list[ChoiceOption]] = relationship(
        order_by="ChoiceOption.position", lazy="selectin"
    )


class ChoiceOption(Base):
    __tablename__ = "choice_options"
    __table_args__ = (
        UniqueConstraint("choice_id", "slug"),
        values_check("action", Action, "action_values"),
        CheckConstraint(SHEET_VALUES, name="sheet_values"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(255))
    when: Mapped[str | None] = mapped_column(String(120))
    action: Mapped[Action | None] = mapped_column(enum_column(Action, 20))
    sheet: Mapped[str | None] = mapped_column(String(20))
    damage_reaction: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)
    grants: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)
    requires: Mapped[dict[str, Any] | None] = mapped_column(NullableJSON)
    position: Mapped[int] = mapped_column(default=0)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)


class CharacterChoicePick(Base):
    __tablename__ = "character_choice_picks"
    __table_args__ = (UniqueConstraint("character_id", "option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"))
    option_id: Mapped[int] = mapped_column(ForeignKey("choice_options.id"))

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

from app.core.db import Base


class Feature(Base):
    """A trait or class feature, like Giant Ancestry or Spellcasting.

    Belongs to exactly one source: a class, a species, a subclass, a background, a feat or an
    item (a magic item's charges and benefits, which apply while it's attuned or carried).
    """

    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint(
            "(class_id IS NOT NULL) + (species_id IS NOT NULL) + (subclass_id IS NOT NULL)"
            " + (background_id IS NOT NULL) + (feat_id IS NOT NULL) + (item_id IS NOT NULL) = 1",
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
        CheckConstraint(
            "action IN ('action', 'bonus_action', 'reaction')", name="action_values"
        ),
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
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)  # full text: private packs, homebrew
    # Gained at this class level (class and subclass features) or character level (species,
    # background, feat and item features).
    level: Mapped[int] = mapped_column(default=1)
    # Class features only: "starting_class" features (like the full starting proficiencies)
    # apply only to a character's first class, "multiclass" ones only to classes added later.
    applies_to: Mapped[str] = mapped_column(String(20), default="all", server_default="all")
    # Limited uses: {"max": 2 | "proficiency_bonus", "recharge": "short_rest" | "long_rest"}.
    uses: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Slot recovery on a short rest: {"budget": "half_class_level", "max_slot_level": 5}.
    slot_recovery: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Attributes it always gives: {"darkvision": 60, "resistances": ["poison"], ...}; see
    # app/features/schema.py:GrantsDef.
    grants: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Something you do (a magic item's Stonecunning): what it takes, and the uses it spends from
    # another feature of the same source (the item's charges). The sheet offers Use for it.
    action: Mapped[str | None] = mapped_column(String(20))  # action, bonus_action, reaction
    spends_feature_id: Mapped[int | None] = mapped_column(ForeignKey("features.id"))
    spends_amount: Mapped[int | None] = mapped_column(SmallInteger)
    position: Mapped[int] = mapped_column(default=0)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)  # removed from its pack

    choices: Mapped[list["Choice"]] = relationship(
        back_populates="feature", order_by="Choice.position", lazy="selectin"
    )
    spells: Mapped[list["FeatureSpell"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class FeatureSpell(Base):
    """A spell a feature gives, like Wondrous Alteration's Alter Self. With `free_cast`, a cast
    can spend `charge_cost` uses of the feature instead of a spell slot. `always_prepared` also
    makes it castable with slots like any prepared spell; without it (a magic item's spell),
    spending the feature's uses is the only way to cast it."""

    __tablename__ = "feature_spells"

    feature_id: Mapped[int] = mapped_column(
        ForeignKey("features.id", ondelete="CASCADE"), primary_key=True
    )
    spell_id: Mapped[int] = mapped_column(ForeignKey("spells.id"), primary_key=True)
    free_cast: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    charge_cost: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    always_prepared: Mapped[bool] = mapped_column(default=True, server_default=text("1"))
    note: Mapped[str | None] = mapped_column(String(255))  # shown on the spell

    spell: Mapped["Spell"] = relationship(lazy="joined")  # noqa: F821


class Choice(Base):
    """A "pick N" decision that comes with a feature. `kind` decides where the
    options come from and where picks are saved (see app/features/kinds.py)."""

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
    # Available once the class (or, for species, the character) reaches this level, as well as
    # the feature's own level. Lets one feature hold choices that unlock over time, like the
    # Wizard's two new spellbook spells per level.
    level: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Picked on the Play sheet rather than the Build page, because it changes during play.
    in_play: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    position: Mapped[int] = mapped_column(default=0)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)  # removed from its pack

    feature: Mapped[Feature] = relationship(back_populates="choices", lazy="joined")
    options: Mapped[list["ChoiceOption"]] = relationship(
        order_by="ChoiceOption.position", lazy="selectin"
    )


class ChoiceOption(Base):
    """An option for a choice of kind "option", e.g. Fire's Burn for Giant Ancestry."""

    __tablename__ = "choice_options"
    __table_args__ = (UniqueConstraint("choice_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(255))
    # When it's used, e.g. "Reaction, when you take damage".
    when: Mapped[str | None] = mapped_column(String(120))
    # {"kind": "reduce" | "retaliate", "dice": "1d12", "ability": "CON", ...}; see
    # app/features/schema.py:DamageReactionDef.
    damage_reaction: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # While picked: {"save_proficiencies": ["CON"]}; see app/features/schema.py:GrantsDef.
    grants: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    position: Mapped[int] = mapped_column(default=0)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)  # removed from its pack


class CharacterChoicePick(Base):
    """A character's pick for a choice of kind "option"."""

    __tablename__ = "character_choice_picks"
    __table_args__ = (UniqueConstraint("character_id", "option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"))
    option_id: Mapped[int] = mapped_column(ForeignKey("choice_options.id"))

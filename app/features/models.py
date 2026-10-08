from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Feature(Base):
    """A trait or class feature, like Giant Ancestry or Spellcasting.

    Belongs to exactly one source. Subclasses, backgrounds and feats will get
    their own nullable column here, covered by the same check.
    """

    __tablename__ = "features"
    __table_args__ = (
        CheckConstraint("(class_id IS NULL) <> (species_id IS NULL)", name="ck_features_one_source"),
        UniqueConstraint("class_id", "slug"),
        UniqueConstraint("species_id", "slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    class_id: Mapped[int | None] = mapped_column(ForeignKey("classes.id"))
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(String(500))
    level: Mapped[int] = mapped_column(default=1)  # character level the feature is gained at
    position: Mapped[int] = mapped_column(default=0)

    choices: Mapped[list["Choice"]] = relationship(
        back_populates="feature", order_by="Choice.position", lazy="selectin"
    )


class Choice(Base):
    """A "pick N" decision that comes with a feature. `kind` decides where the
    options come from and where picks are saved (see app/features/kinds.py)."""

    __tablename__ = "choices"
    __table_args__ = (UniqueConstraint("feature_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id"))
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    count: Mapped[int] = mapped_column(default=1)
    criteria: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(default=0)

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
    position: Mapped[int] = mapped_column(default=0)


class CharacterChoicePick(Base):
    """A character's pick for a choice of kind "option"."""

    __tablename__ = "character_choice_picks"
    __table_args__ = (UniqueConstraint("character_id", "option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"))
    option_id: Mapped[int] = mapped_column(ForeignKey("choice_options.id"))

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CharacterPlayState(Base):
    __tablename__ = "character_play_states"
    __table_args__ = (
        CheckConstraint("current_hp >= 0", name="current_hp_non_negative"),
        CheckConstraint("temp_hp >= 0", name="temp_hp_non_negative"),
        CheckConstraint(
            "cp >= 0 AND sp >= 0 AND ep >= 0 AND gp >= 0 AND pp >= 0", name="coins_non_negative"
        ),
    )

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    current_hp: Mapped[int | None] = mapped_column(SmallInteger)
    temp_hp: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    temp_hp_source: Mapped[str | None] = mapped_column(String(80))
    cp: Mapped[int] = mapped_column(default=0, server_default="0")
    sp: Mapped[int] = mapped_column(default=0, server_default="0")
    ep: Mapped[int] = mapped_column(default=0, server_default="0")
    gp: Mapped[int] = mapped_column(default=0, server_default="0")
    pp: Mapped[int] = mapped_column(default=0, server_default="0")


class CharacterHpEffect(Base):
    __tablename__ = "character_hp_effects"
    __table_args__ = (CheckConstraint("max_hp_delta <> 0", name="max_hp_delta_non_zero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(80))
    max_hp_delta: Mapped[int] = mapped_column(SmallInteger)
    spell_id: Mapped[int | None] = mapped_column(ForeignKey("spells.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CharacterAcEffect(Base):
    __tablename__ = "character_ac_effects"
    __table_args__ = (
        CheckConstraint("kind IN ('base', 'bonus', 'minimum')", name="kind_values"),
        CheckConstraint(
            "(kind = 'bonus' AND value <> 0) OR (kind <> 'bonus' AND value BETWEEN 10 AND 30)",
            name="value_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[int] = mapped_column(SmallInteger)
    spell_id: Mapped[int | None] = mapped_column(ForeignKey("spells.id"))
    ends_on_long_rest: Mapped[bool] = mapped_column(default=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CharacterPreparedSpell(Base):
    __tablename__ = "character_prepared_spells"
    __table_args__ = (
        ForeignKeyConstraint(
            ["character_id", "spell_id"],
            ["spellbook_entries.character_id", "spellbook_entries.spell_id"],
            name="fk_character_prepared_spells_spellbook_entries",
            ondelete="CASCADE",
        ),
    )

    character_id: Mapped[int] = mapped_column(primary_key=True)
    spell_id: Mapped[int] = mapped_column(primary_key=True)


class CharacterSpellSlot(Base):
    __tablename__ = "character_spell_slots"
    __table_args__ = (
        CheckConstraint("slot_level BETWEEN 1 AND 9", name="slot_level_range"),
        CheckConstraint("expended >= 0", name="expended_non_negative"),
        CheckConstraint("kind IN ('spellcasting', 'pact')", name="kind_values"),
    )

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(
        String(20), primary_key=True, default="spellcasting", server_default="spellcasting"
    )
    slot_level: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    expended: Mapped[int] = mapped_column(SmallInteger, default=0)


class CharacterFeatureUse(Base):
    __tablename__ = "character_feature_uses"
    __table_args__ = (CheckConstraint("expended >= 0", name="expended_non_negative"),)

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    feature_id: Mapped[int] = mapped_column(ForeignKey("features.id"), primary_key=True)
    expended: Mapped[int] = mapped_column(SmallInteger, default=0)


class CharacterHitDice(Base):
    __tablename__ = "character_hit_dice"
    __table_args__ = (CheckConstraint("spent >= 0", name="spent_non_negative"),)

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"), primary_key=True)
    spent: Mapped[int] = mapped_column(SmallInteger, default=0)

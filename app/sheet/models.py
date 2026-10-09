"""Play-time state tracked on the character sheet (as opposed to the character's build)."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CharacterPlayState(Base):
    """Current hit points and temporary hit points. One row per character, created the first
    time something changes.

    Current HP is stored rather than "damage taken" because effects that raise max HP (like
    Aid) end by only capping current HP; see app/sheet/rules.py.
    """

    __tablename__ = "character_play_states"
    __table_args__ = (
        CheckConstraint("current_hp >= 0", name="current_hp_non_negative"),
        CheckConstraint("temp_hp >= 0", name="temp_hp_non_negative"),
    )

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    current_hp: Mapped[int | None] = mapped_column(SmallInteger)  # NULL = at full HP
    temp_hp: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    temp_hp_source: Mapped[str | None] = mapped_column(String(80))  # e.g. "False Life"


class CharacterHpEffect(Base):
    """An active effect that raises or lowers max HP, like Aid (+5) or a life drain (-4)."""

    __tablename__ = "character_hp_effects"
    __table_args__ = (CheckConstraint("max_hp_delta <> 0", name="max_hp_delta_non_zero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(80))
    max_hp_delta: Mapped[int] = mapped_column(SmallInteger)
    # Where the effect came from, once spells declare their effects (e.g. Aid).
    spell_id: Mapped[int | None] = mapped_column(ForeignKey("spells.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CharacterPreparedSpell(Base):
    """A spellbook spell the character has prepared.

    The composite foreign key into spellbook_entries means only spells in the book can be
    prepared, and a spell leaving the book (e.g. removing a level) unprepares it too.
    """

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
    """Spell slots used at one slot level. The maximum is calculated from class levels
    (app/sheet/slots.py), so this stores slots *used*: gaining a level adds slots that are
    available right away."""

    __tablename__ = "character_spell_slots"
    __table_args__ = (
        CheckConstraint("slot_level BETWEEN 1 AND 9", name="slot_level_range"),
        CheckConstraint("expended >= 0", name="expended_non_negative"),
    )

    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    slot_level: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    expended: Mapped[int] = mapped_column(SmallInteger, default=0)

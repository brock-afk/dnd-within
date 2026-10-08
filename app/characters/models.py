from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.abilities.rules import ABILITIES
from app.classes.models import CharacterClassLevel
from app.core.db import Base
from app.leveling.models import CharacterLevel
from app.species.models import Species

_SCORE_COLUMNS = [a.column for a in ABILITIES]


class Character(Base):
    __tablename__ = "characters"
    __table_args__ = (
        CheckConstraint(
            "ability_method IN ('standard_array', 'point_buy', 'manual')",
            name="ability_method_values",
        ),
        # Scores and method are set together or not at all.
        CheckConstraint(
            "(ability_method IS NULL AND "
            + " AND ".join(f"{c} IS NULL" for c in _SCORE_COLUMNS)
            + ") OR (ability_method IS NOT NULL AND "
            + " AND ".join(f"{c} IS NOT NULL" for c in _SCORE_COLUMNS)
            + ")",
            name="abilities_all_or_none",
        ),
        *(CheckConstraint(f"{c} BETWEEN 3 AND 18", name=f"{c}_range") for c in _SCORE_COLUMNS),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Base ability scores, before bonuses (see app/abilities). NULL until the player sets them.
    ability_method: Mapped[str | None] = mapped_column(String(20))
    strength: Mapped[int | None] = mapped_column(SmallInteger)
    dexterity: Mapped[int | None] = mapped_column(SmallInteger)
    constitution: Mapped[int | None] = mapped_column(SmallInteger)
    intelligence: Mapped[int | None] = mapped_column(SmallInteger)
    wisdom: Mapped[int | None] = mapped_column(SmallInteger)
    charisma: Mapped[int | None] = mapped_column(SmallInteger)

    species: Mapped[Species] = relationship(lazy="joined")
    classes: Mapped[list[CharacterClassLevel]] = relationship(
        back_populates="character",
        order_by=CharacterClassLevel.position,
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Level history, one row per level gained (see app/leveling).
    levels: Mapped[list[CharacterLevel]] = relationship(
        order_by=CharacterLevel.character_level,
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def level(self) -> int:
        """Character level: how many levels the character has gained, across all classes."""
        return len(self.levels)

    def class_level(self, class_id: int) -> int:
        return sum(1 for lv in self.levels if lv.class_id == class_id)

    @property
    def class_summary(self) -> str:
        """"Wizard (Evoker)" for a single class, "Wizard 3 (Evoker) / Fighter 2" when
        multiclassed. The subclass appears once one is chosen."""

        def label(cc: CharacterClassLevel, with_level: bool) -> str:
            text = cc.character_class.name + (f" {cc.level}" if with_level else "")
            return f"{text} ({cc.subclass.name})" if cc.subclass else text

        if len(self.classes) == 1:
            return label(self.classes[0], with_level=False)
        return " / ".join(label(cc, with_level=True) for cc in self.classes)

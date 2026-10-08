from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.abilities.rules import ABILITIES
from app.classes.models import CharacterClassLevel
from app.core.db import Base
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
        order_by=CharacterClassLevel.position,
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def level(self) -> int:
        """Character level: the total of all class levels."""
        return sum(cc.level for cc in self.classes)

    @property
    def class_summary(self) -> str:
        """"Wizard" for a single class, "Wizard 3 / Fighter 2" when multiclassed."""
        if len(self.classes) == 1:
            return self.classes[0].character_class.name
        return " / ".join(f"{cc.character_class.name} {cc.level}" for cc in self.classes)

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CharacterAbilityBonus(Base):
    """An increase to one ability from a choice (a background's +2/+1, a level 4 increase, ...).

    Kept apart from the base scores on Character, so changing a background or redoing
    a choice never corrupts the scores the player rolled or bought.
    """

    __tablename__ = "character_ability_bonuses"
    __table_args__ = (
        UniqueConstraint("character_id", "choice_id", "ability"),
        CheckConstraint(
            "ability IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA')", name="ability_values"
        ),
        CheckConstraint("amount BETWEEN 1 AND 2", name="amount_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"))
    ability: Mapped[str] = mapped_column(String(3))
    amount: Mapped[int]

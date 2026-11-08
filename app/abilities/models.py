from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.abilities.rules import Ability
from app.core.db import Base, enum_column


class CharacterAbilityBonus(Base):
    __tablename__ = "character_ability_bonuses"
    __table_args__ = (
        UniqueConstraint("character_id", "choice_id", "ability"),
        CheckConstraint("amount BETWEEN 1 AND 2", name="amount_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    choice_id: Mapped[int] = mapped_column(ForeignKey("choices.id"))
    ability: Mapped[Ability] = mapped_column(enum_column(Ability, 3, check="ability_values"))
    amount: Mapped[int]

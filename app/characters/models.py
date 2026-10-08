from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.classes.models import CharacterClassLevel
from app.core.db import Base
from app.species.models import Species


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

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

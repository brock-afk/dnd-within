from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.classes.models import CharacterClass
from app.core.db import Base
from app.species.models import Species


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.id"))
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    character_class: Mapped[CharacterClass] = relationship(lazy="joined")
    species: Mapped[Species] = relationship(lazy="joined")

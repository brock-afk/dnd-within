from sqlalchemy import SmallInteger, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.content.models import ContentMixin
from app.core.db import Base


class Species(ContentMixin, Base):
    __tablename__ = "species"
    __table_args__ = (UniqueConstraint("source_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(255))
    speed: Mapped[int] = mapped_column(SmallInteger, default=30, server_default="30")  # feet

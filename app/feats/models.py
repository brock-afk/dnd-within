from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.content.models import ContentMixin
from app.core.db import Base


class Feat(ContentMixin, Base):
    __tablename__ = "feats"
    __table_args__ = (
        UniqueConstraint("source_id", "slug"),
        CheckConstraint("category IN ('origin', 'general')", name="category_values"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    category: Mapped[str] = mapped_column(String(20), default="origin")
    summary: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

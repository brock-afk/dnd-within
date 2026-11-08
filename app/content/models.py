from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("kind IN ('official', 'third_party', 'homebrew')", name="kind_values"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    pack_version: Mapped[str | None] = mapped_column(String(40))
    pack_checksum: Mapped[str | None] = mapped_column(String(64))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContentMixin:
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)

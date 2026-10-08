from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Source(Base):
    """Where content comes from: a book (one content pack) or a user's homebrew.

    Every content row (classes, species, spells, ...) belongs to one source, and slugs only
    have to be unique within a source, so two books can both have an "evoker".
    """

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("kind IN ('official', 'third_party', 'homebrew')", name="kind_values"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Set by the content importer; lets startup skip packs that haven't changed.
    pack_version: Mapped[str | None] = mapped_column(String(40))
    pack_checksum: Mapped[str | None] = mapped_column(String(64))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContentMixin:
    """Columns every top-level content table shares: its source, and when (if ever) it was
    removed from its pack. Retired rows are kept because characters may still use them."""

    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime)

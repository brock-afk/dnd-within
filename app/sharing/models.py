from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CharacterShare(Base):
    """Who else can view a character, read-only. Either a secret link anyone with it can open
    (`token`), or, later, a specific user (`user_id`). A character has at most one link at a
    time: making a new one replaces it, so the old URL stops working."""

    __tablename__ = "character_shares"
    __table_args__ = (
        CheckConstraint("(token IS NULL) <> (user_id IS NULL)", name="token_or_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str | None] = mapped_column(String(64), unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

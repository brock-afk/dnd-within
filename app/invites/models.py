from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.core.db import Base


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint("used_at IS NULL OR revoked_at IS NULL", name="used_or_revoked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    note: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
    used_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    used_by: Mapped[User | None] = relationship()

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.content.models import ContentMixin
from app.core.db import Base
from app.feats.models import Feat


class Background(ContentMixin, Base):
    """A background, like Sage. Its ability score increases, skills and tools are features
    with choices (features.background_id); `feat` is the origin feat it gives."""

    __tablename__ = "backgrounds"
    __table_args__ = (UniqueConstraint("source_id", "slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)  # full text: private packs, homebrew
    feat_id: Mapped[int] = mapped_column(ForeignKey("feats.id"))

    feat: Mapped[Feat] = relationship(lazy="joined")

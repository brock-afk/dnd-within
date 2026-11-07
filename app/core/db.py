from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import JSON, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


# Every index and constraint gets a predictable name, so migrations can refer to them
# by name and every database built from the migrations is identical.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# For nullable JSON columns: None is stored as SQL NULL, not the JSON value null, so
# `column.is_(None)` / `is_not(None)` filters work.
NullableJSON = JSON(none_as_null=True)


def get_db() -> Iterator[Session]:
    """One transaction per request, so a change made in several steps is saved whole or not
    at all. Leaving the `with` after an exception rolls back."""
    with SessionLocal() as db:
        yield db
        db.commit()


# Function scope commits before the response is sent: a failed commit is an error response,
# never a page showing changes that weren't saved.
DbSession = Annotated[Session, Depends(get_db, scope="function")]


def reload_all(db: Session) -> None:
    """Rows and relationships loaded before a change would render stale."""
    db.flush()  # expiring drops changes not yet sent to the database
    db.expire_all()

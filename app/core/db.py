from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated

from fastapi import Depends
from sqlalchemy import JSON, CheckConstraint, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


NullableJSON = JSON(none_as_null=True)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
        db.commit()


DbSession = Annotated[Session, Depends(get_db, scope="function")]


def values_check(column: str, values: type[StrEnum], name: str) -> CheckConstraint:
    listed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({listed})", name=name)


def release_connection(db: Session) -> None:
    db.commit()


def reload_all(db: Session) -> None:
    db.flush()
    db.expire_all()

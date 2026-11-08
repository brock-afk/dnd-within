from collections.abc import Iterator
from enum import StrEnum
from typing import Annotated

from fastapi import Depends
from sqlalchemy import JSON, Enum, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapper, Session, sessionmaker

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


def enum_column(values: type[StrEnum], length: int, check: str) -> Enum:
    return Enum(
        values,
        native_enum=False,
        create_constraint=True,
        name=check,
        length=length,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )


@event.listens_for(Mapper, "mapper_configured")
def _enum_attributes_hold_members(mapper: Mapper, cls: type) -> None:
    for prop in mapper.column_attrs:
        column_type = prop.columns[0].type
        if isinstance(column_type, Enum) and column_type.enum_class is not None:
            to_member = _member_of(column_type.enum_class)
            event.listen(getattr(cls, prop.key), "set", to_member, retval=True)


def _member_of(enum_class: type[StrEnum]):
    def to_member(target, value, oldvalue, initiator):
        return value if value is None else enum_class(value)

    return to_member


def release_connection(db: Session) -> None:
    db.commit()


def reload_all(db: Session) -> None:
    db.flush()
    db.expire_all()

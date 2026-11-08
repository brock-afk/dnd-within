from sqlalchemy import ColumnElement, and_, select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.sharing.models import CharacterShare


def public_link(character: Character) -> ColumnElement[bool]:
    return and_(CharacterShare.character_id == character.id, CharacterShare.token.is_not(None))


def public_share(db: Session, character: Character) -> CharacterShare | None:
    return db.scalar(select(CharacterShare).where(public_link(character)))


def shared_character(db: Session, token: str) -> Character | None:
    return db.scalar(
        select(Character)
        .join(CharacterShare, CharacterShare.character_id == Character.id)
        .where(CharacterShare.token == token)
    )

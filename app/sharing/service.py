import secrets

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.sharing.models import CharacterShare
from app.sharing.queries import public_link


def make_link(db: Session, character: Character) -> CharacterShare:
    stop_sharing(db, character)
    share = CharacterShare(character_id=character.id, token=secrets.token_urlsafe(24))
    db.add(share)
    db.flush()
    return share


def stop_sharing(db: Session, character: Character) -> None:
    db.execute(delete(CharacterShare).where(public_link(character)))

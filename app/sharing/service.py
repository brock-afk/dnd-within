"""Sharing a character read-only. For now that's one public link per character: a secret
token in the URL that anyone can open without an account."""

import secrets

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.sharing.models import CharacterShare


def public_share(db: Session, character: Character) -> CharacterShare | None:
    """The character's public link, if it's shared."""
    return db.scalar(
        select(CharacterShare).where(
            CharacterShare.character_id == character.id, CharacterShare.token.is_not(None)
        )
    )


def make_link(db: Session, character: Character) -> CharacterShare:
    """Share publicly with a fresh link. An existing link is replaced, so it stops working.
    Doesn't commit."""
    stop_sharing(db, character)
    share = CharacterShare(character_id=character.id, token=secrets.token_urlsafe(24))
    db.add(share)
    db.flush()
    return share


def stop_sharing(db: Session, character: Character) -> None:
    """Turn the public link off. Doesn't commit."""
    db.execute(
        delete(CharacterShare).where(
            CharacterShare.character_id == character.id, CharacterShare.token.is_not(None)
        )
    )


def shared_character(db: Session, token: str) -> Character | None:
    """The character a public link points at, or None if there's no such link (anymore)."""
    share = db.scalar(select(CharacterShare).where(CharacterShare.token == token))
    return db.get(Character, share.character_id) if share else None

"""Integration tests run on a real MySQL database (dnd_within_test, see tests/conftest.py):
migrated to head and loaded with the committed content packs once per run. Each test runs in a
transaction that's rolled back afterwards."""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.characters.models import Character
from app.classes.models import CharacterClass, CharacterClassLevel
from app.content.importer import import_packs
from app.core.db import SessionLocal, engine
from app.leveling.models import CharacterLevel
from app.species.models import Species


@pytest.fixture(scope="session")
def database():
    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal() as db:
        assert import_packs(db), "a content pack failed to import"


@pytest.fixture
def db(database):
    with engine.connect() as connection:
        transaction = connection.begin()
        # Commits inside the code under test become savepoints, so the rollback undoes them.
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        transaction.rollback()


@pytest.fixture
def character(db) -> Character:
    """A level 1 Goliath Wizard with Constitution 14: 8 max HP (d6 + 2)."""
    user = User(username="tester", password_hash="x")
    wizard = db.scalar(select(CharacterClass).where(CharacterClass.slug == "wizard"))
    goliath = db.scalar(select(Species).where(Species.slug == "goliath"))
    db.add(user)
    db.flush()
    character = Character(
        user_id=user.id,
        name="Test",
        species_id=goliath.id,
        ability_method="manual",
        strength=10,
        dexterity=10,
        constitution=14,
        intelligence=15,
        wisdom=10,
        charisma=10,
    )
    character.classes.append(CharacterClassLevel(class_id=wizard.id, position=0))
    character.levels.append(CharacterLevel(character_level=1, class_id=wizard.id, hp_method="max"))
    db.add(character)
    db.flush()
    db.refresh(character)
    return character

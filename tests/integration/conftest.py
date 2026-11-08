import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.auth.models import User
from app.auth.security import hash_password
from app.backgrounds.models import Background
from app.characters.models import Character
from app.characters.origins import BACKGROUND
from app.characters.service import choose_origin
from app.classes.models import CharacterClass, CharacterClassLevel
from app.content.importer import import_packs
from app.content.models import Source
from app.core.db import SessionLocal, engine, get_db
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature
from app.inventory.models import CharacterItem, Item
from app.leveling.models import CharacterLevel
from app.main import app
from app.sheet.models import CharacterPreparedSpell
from app.species.models import Species
from app.spells.models import SpellbookEntry

PASSWORD = "test password"
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session")
def database():
    command.upgrade(Config("alembic.ini"), "head")
    with SessionLocal() as db:
        assert import_packs(db), "a content pack failed to import"


@pytest.fixture
def db(database):
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as session:
            yield session
        transaction.rollback()


@pytest.fixture
def character(db) -> Character:
    user = User(username="tester", password_hash=PASSWORD_HASH)
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


@pytest.fixture
def owner(db, character) -> User:
    return db.get(User, character.user_id)


@pytest.fixture
def other_user(db) -> User:
    user = User(username="someone-else", password_hash="x")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def theirs(db, character, other_user) -> Character:
    theirs = Character(user_id=other_user.id, name="Theirs", species_id=character.species_id)
    class_id = character.classes[0].class_id
    theirs.classes.append(CharacterClassLevel(class_id=class_id, position=0))
    theirs.levels.append(CharacterLevel(character_level=1, class_id=class_id, hp_method="max"))
    db.add(theirs)
    db.commit()
    return theirs


@pytest.fixture
def wanderer(db) -> Background:
    return db.scalar(select(Background).where(Background.slug == "test-wanderer"))


@pytest.fixture
def prepare_from_book(db):

    def prepare_from_book(character: Character, spell_id: int) -> None:
        db.add(SpellbookEntry(character_id=character.id, spell_id=spell_id, acquired_via="copied"))
        db.flush()
        db.add(CharacterPreparedSpell(character_id=character.id, spell_id=spell_id))
        db.flush()

    return prepare_from_book


@pytest.fixture
def wizard_choice(db):

    def wizard_choice(slug: str) -> Choice:
        return db.scalar(
            select(Choice)
            .join(Feature, Feature.id == Choice.feature_id)
            .join(CharacterClass, CharacterClass.id == Feature.class_id)
            .where(CharacterClass.slug == "wizard", Choice.slug == slug)
        )

    return wizard_choice


@pytest.fixture
def increase(db, character, wanderer) -> Choice:
    choose_origin(db, character, BACKGROUND, str(wanderer.id))
    return db.scalar(select(Choice).join(Feature).where(Feature.background_id == wanderer.id))


@pytest.fixture
def stone_giant(db, character) -> Character:
    stone = db.scalar(select(ChoiceOption).where(ChoiceOption.slug == "stone"))
    db.add(
        CharacterChoicePick(
            character_id=character.id, choice_id=stone.choice_id, option_id=stone.id
        )
    )
    db.flush()
    return character


@pytest.fixture
def serve_with():

    def serve(session: Session) -> None:
        def get_test_db():
            try:
                yield session
            except Exception:
                session.rollback()
                raise
            session.commit()

        app.dependency_overrides[get_db] = get_test_db

    yield serve
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def visitor(db, serve_with) -> TestClient:
    serve_with(db)
    return TestClient(app)


@pytest.fixture
def password() -> str:
    return PASSWORD


@pytest.fixture
def client(db, character, serve_with):
    serve_with(db)
    client = TestClient(app)
    user = db.get(User, character.user_id)
    response = client.post("/login", data={"username": user.username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    yield client


@pytest.fixture
def warlock(db, character) -> Character:
    pact = db.scalar(select(CharacterClass.id).where(CharacterClass.slug == "test-pact"))
    warlock = Character(
        user_id=character.user_id,
        name="Pact",
        species_id=character.species_id,
        ability_method="manual",
        **dict.fromkeys(["strength", "dexterity", "constitution", "intelligence", "wisdom"], 10),
        charisma=15,
    )
    warlock.classes.append(CharacterClassLevel(class_id=pact, position=0))
    warlock.levels.append(CharacterLevel(character_level=1, class_id=pact, hp_method="max"))
    db.add(warlock)
    db.flush()
    db.refresh(warlock)
    return warlock


@pytest.fixture
def level_up(db):

    def level_up(character: Character, level: int) -> None:
        class_id = character.classes[0].class_id
        for n in range(character.level + 1, level + 1):
            character.levels.append(
                CharacterLevel(character_level=n, class_id=class_id, hp_method="fixed")
            )
        db.flush()

    return level_up


@pytest.fixture
def charged_item(db):

    def charged_item(character: Character, uses: dict, attuned: bool = True) -> Feature:
        source = db.scalar(select(Source).where(Source.slug == "test-core"))
        item = Item(
            source_id=source.id,
            slug="test-wand",
            name="Test Wand",
            category="magic",
            rarity="uncommon",
            summary="",
            requires_attunement=True,
        )
        db.add(item)
        db.flush()
        charges = Feature(item_id=item.id, slug="charges", name="Charges", summary="", uses=uses)
        carried = CharacterItem(character_id=character.id, item_id=item.id, attuned=attuned)
        db.add_all([charges, carried])
        db.flush()
        return charges

    return charged_item

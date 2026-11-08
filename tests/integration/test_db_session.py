import pytest
from sqlalchemy import delete, select
from starlette.testclient import TestClient

from app.auth.models import User
from app.auth.security import hash_password
from app.characters.models import Character
from app.classes.models import CharacterClass
from app.core.db import SessionLocal, engine, get_db, release_connection
from app.main import app
from app.species.models import Species

USERNAME = "get-db-test"
PASSWORD = "test password"


def _user_id() -> int | None:
    with SessionLocal() as check:
        return check.scalar(select(User.id).where(User.username == USERNAME))


@pytest.fixture
def cleanup():
    yield
    with SessionLocal() as db:
        db.execute(delete(User).where(User.username == USERNAME))
        db.commit()


def test_release_connection_returns_it_to_the_pool(database):
    before = engine.pool.checkedout()
    with SessionLocal() as db:
        db.scalar(select(User.id).limit(1))
        assert engine.pool.checkedout() == before + 1
        release_connection(db)
        assert engine.pool.checkedout() == before


def test_route_returning_commits(database, cleanup):
    request = get_db()
    db = next(request)
    db.add(User(username=USERNAME, password_hash="x"))
    with pytest.raises(StopIteration):
        next(request)
    assert _user_id() is not None


def test_route_raising_saves_nothing(database, cleanup):
    request = get_db()
    db = next(request)
    db.add(User(username=USERNAME, password_hash="x"))
    db.flush()
    with pytest.raises(RuntimeError):
        request.throw(RuntimeError("the route failed partway"))
    assert _user_id() is None


def test_app_saves_route_changes(database, cleanup):
    with SessionLocal() as db:
        db.add(User(username=USERNAME, password_hash=hash_password(PASSWORD)))
        db.commit()
        wizard = db.scalar(select(CharacterClass.id).where(CharacterClass.slug == "wizard"))
        goliath = db.scalar(select(Species.id).where(Species.slug == "goliath"))
    client = TestClient(app)
    client.post("/login", data={"username": USERNAME, "password": PASSWORD})

    response = client.post(
        "/characters", data={"name": "Saved", "class_id": wizard, "species_id": goliath}
    )

    assert response.status_code == 200, response.text
    with SessionLocal() as check:
        assert check.scalar(select(Character.id).where(Character.user_id == _user_id()))

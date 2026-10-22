"""get_db's transaction per request, on real sessions: these commit to the test database, so
they clean up after themselves."""

import pytest
from sqlalchemy import delete, select
from starlette.testclient import TestClient

from app.auth.models import User
from app.auth.security import hash_password
from app.characters.models import Character
from app.classes.models import CharacterClass
from app.core.db import SessionLocal, get_db
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
        db.execute(delete(User).where(User.username == USERNAME))  # cascades to characters
        db.commit()


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
    db.flush()  # sent to the database, but not committed
    with pytest.raises(RuntimeError):
        request.throw(RuntimeError("the route failed partway"))
    assert _user_id() is None


def test_app_saves_route_changes(database, cleanup):
    """Through the real app: creating a character saves it, though the route never commits."""
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

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.core.db import get_db
from app.main import app


def test_healthy_with_database(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).get("/healthz")
    finally:
        app.dependency_overrides.pop(get_db)
    assert response.status_code == 200
    assert response.text == "ok"


def test_unhealthy_without_database():
    # A real connection to a port nothing listens on.
    unreachable = create_engine("mysql+pymysql://dnd:x@127.0.0.1:1/none")
    with Session(unreachable) as db:
        app.dependency_overrides[get_db] = lambda: db
        try:
            response = TestClient(app).get("/healthz")
        finally:
            app.dependency_overrides.pop(get_db)
    unreachable.dispose()
    assert response.status_code == 503

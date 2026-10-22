from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from starlette.testclient import TestClient

from app.main import app


def test_healthy_with_database(db, serve_with):
    serve_with(db)
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"


def test_unhealthy_without_database(serve_with):
    # A real connection to a port nothing listens on.
    unreachable = create_engine("mysql+pymysql://dnd:x@127.0.0.1:1/none")
    with Session(unreachable) as db:
        serve_with(db)
        response = TestClient(app).get("/healthz")
    unreachable.dispose()
    assert response.status_code == 503

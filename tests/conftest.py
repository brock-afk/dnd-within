import os

os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "dnd_within_test")
os.environ["CONTENT_PATHS"] = "tests/fixtures/content"

import threading  # noqa: E402

import pytest  # noqa: E402

from app import models  # noqa: E402, F401
from app.auth import security  # noqa: E402


@pytest.fixture
def busy_hasher(monkeypatch):
    monkeypatch.setattr(security, "_slots", threading.BoundedSemaphore(0))
    monkeypatch.setattr(security, "SLOT_WAIT_SECONDS", 0.01)

import os

os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "dnd_within_test")
os.environ["CONTENT_PATHS"] = "tests/fixtures/content"

import pytest  # noqa: E402

from app import models  # noqa: E402, F401
from app.auth import dependencies  # noqa: E402
from app.auth.limits import AttemptLimiter, auth_attempts  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_attempt_limiter(monkeypatch):
    limiter = AttemptLimiter(auth_attempts.limit, auth_attempts.window)
    monkeypatch.setattr(dependencies, "auth_attempts", limiter)

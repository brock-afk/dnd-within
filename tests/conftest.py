import os

os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "dnd_within_test")
os.environ["CONTENT_PATHS"] = "tests/fixtures/content"

from app import models  # noqa: E402, F401

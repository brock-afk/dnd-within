import os

# Integration tests use their own database, never the dev data, and only the fixture pack.
# Set before anything imports app.core.config.
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "dnd_within_test")
os.environ["CONTENT_PATHS"] = "tests/fixtures/content"

# Registers every table so models can be built without a database.
from app import models  # noqa: E402, F401

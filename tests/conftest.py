import os

# Integration tests use their own database, never the dev data, and only committed content.
# Set before anything imports app.core.config.
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "dnd_within_test")
os.environ["CONTENT_PATHS"] = "content"

# Registers every table so models can be built without a database.
from app import models  # noqa: E402, F401

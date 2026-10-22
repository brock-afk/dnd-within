import logging

from app.content import loader
from app.content.importer import import_packs


def test_no_packs_found_is_logged_and_fails(db, monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(loader.settings, "content_paths", str(tmp_path))
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        assert import_packs(db) is False
    assert f"No content packs found in CONTENT_PATHS ({tmp_path})" in caplog.text

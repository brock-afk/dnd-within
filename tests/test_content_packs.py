from pathlib import Path

from app.content import loader

CONTENT = Path(__file__).resolve().parents[1] / "content"


def test_committed_packs_are_valid(monkeypatch):
    # Only committed packs: content-private isn't available in CI.
    monkeypatch.setattr(loader.settings, "content_paths", str(CONTENT))
    packs = loader.discover()
    assert packs, "no content packs found"
    for pack in packs:
        assert pack.errors == [], f"{pack.slug}: {pack.errors}"

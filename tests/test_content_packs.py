from pathlib import Path

import pytest
from pydantic import ValidationError

from app.content import loader
from app.content.schema import ItemDef
from app.features.schema import UsesDef

ROOT = Path(__file__).resolve().parents[1]


# content/ is still committed until the packs move to their own repo.
@pytest.mark.parametrize("folder", [ROOT / "tests/fixtures/content", ROOT / "content"])
def test_committed_packs_are_valid(monkeypatch, folder):
    monkeypatch.setattr(loader.settings, "content_paths", str(folder))
    packs = loader.discover()
    assert packs, "no content packs found"
    for pack in packs:
        assert pack.errors == [], f"{pack.slug}: {pack.errors}"


def _item(healing: str) -> ItemDef:
    return ItemDef(
        slug="potion", name="Potion", category="consumable", summary="Heals.", healing=healing
    )


@pytest.mark.parametrize("healing", ["2d4+2", "999d999+999", "5"])
def test_item_healing_accepts_dice_up_to_three_digits(healing):
    assert _item(healing).healing == healing


@pytest.mark.parametrize("healing", ["1000d4", "2d1000", "2d4+1000", "1000", "99999999999999999d9"])
def test_item_healing_rejects_oversized_dice(healing):
    with pytest.raises(ValidationError):
        _item(healing)


def test_uses_regain_rejects_oversized_dice():
    assert UsesDef(max=3, recharge="dawn", regain="1d3").regain == "1d3"
    with pytest.raises(ValidationError):
        UsesDef(max=3, recharge="dawn", regain="99999999d9")

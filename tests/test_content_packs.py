import pytest
from pydantic import ValidationError

from app.content import loader
from app.content.schema import ItemDef
from app.features.schema import ChoiceDef, OptionDef, UsesDef


def test_fixture_packs_are_valid():
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


def _option(features: list[dict]) -> dict:
    return {"slug": "infernal", "name": "Infernal", "summary": "A legacy.", "features": features}


def test_option_features_cant_have_choices():
    nested = {"slug": "pick", "name": "Pick", "kind": "skill"}
    feature = {"slug": "spell", "name": "Spell", "summary": "A spell.", "choices": [nested]}
    with pytest.raises(ValidationError, match="an option's features can't have choices"):
        OptionDef.model_validate(_option([feature]))


def test_loader_checks_spells_in_option_features(tmp_path, monkeypatch):
    pack = tmp_path / "bad"
    (pack / "species").mkdir(parents=True)
    (pack / "pack.yaml").write_text("slug: bad\nname: Bad\nkind: homebrew\nversion: 1\n")
    (pack / "species" / "folk.yaml").write_text(
        "slug: folk\nname: Folk\nsummary: Folk.\nfeatures:\n"
        "- slug: legacy\n  name: Legacy\n  summary: A legacy.\n  choices:\n"
        "  - slug: legacy\n    name: Legacy\n    kind: option\n    options:\n"
        "    - slug: infernal\n      name: Infernal\n      summary: Fire.\n      features:\n"
        "      - slug: rebuke\n        name: Rebuke\n        summary: A spell.\n"
        "        spells: [{spell: no-such-spell}]\n"
    )
    monkeypatch.setattr(loader.settings, "content_paths", str(tmp_path))

    [found] = loader.discover()

    assert any(
        "species/folk > legacy > legacy > infernal > rebuke > spells" in e and "no-such-spell" in e
        for e in found.errors
    ), found.errors


def _spell_choice(max_level) -> dict:
    return {
        "slug": "spells",
        "name": "Spells",
        "kind": "spell",
        "criteria": {"class": "warlock", "max_level": max_level},
    }


@pytest.mark.parametrize("max_level", [1, 9, "class_slots"])
def test_spell_choice_max_level_accepts_levels_and_class_slots(max_level):
    assert ChoiceDef.model_validate(_spell_choice(max_level)).criteria["max_level"] == max_level


@pytest.mark.parametrize("max_level", [0, 10, "slots", True, 2.5])
def test_spell_choice_max_level_rejects_anything_else(max_level):
    with pytest.raises(ValidationError, match="max_level is a spell level"):
        ChoiceDef.model_validate(_spell_choice(max_level))

import pytest
from pydantic import ValidationError

from app.content import loader
from app.content.schema import ItemDef
from app.features.schema import ChoiceDef, FeatureDef, OptionDef, UsesDef


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


def _feature_with_choice(choice: dict) -> dict:
    return {"slug": "tome", "name": "Tome", "summary": "A book.", "choices": [choice]}


def test_option_features_can_have_choices():
    cantrips = {"slug": "cantrips", "name": "Cantrips", "kind": "spell", "criteria": {"level": 0}}
    option = OptionDef.model_validate(_option([_feature_with_choice(cantrips)]))
    assert option.features[0].choices[0].slug == "cantrips"


def test_nesting_stops_at_options_inside_option_features():
    inner = {
        "slug": "deep",
        "name": "Deep",
        "summary": "Too deep.",
        "features": [{"slug": "x", "name": "X", "summary": "X."}],
    }
    choice = {"slug": "pick", "name": "Pick", "kind": "option", "options": [inner]}
    with pytest.raises(ValidationError, match="can't own features"):
        OptionDef.model_validate(_option([_feature_with_choice(choice)]))


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


def _options(n: int, **first) -> list[dict]:
    return [
        {"slug": f"o{i}", "name": f"O{i}", "summary": "An option.", **(first if i == 0 else {})}
        for i in range(n)
    ]


def _option_choice(count, options) -> dict:
    return {"slug": "inv", "name": "Inv", "kind": "option", "count": count, "options": options}


def test_choice_count_can_grow_with_level():
    table = [1, 3, 3, 3, 5] + [5] * 15
    assert ChoiceDef.model_validate(_option_choice(table, _options(5))).max_count == 5
    with pytest.raises(ValidationError, match="needs at least 5 options"):
        ChoiceDef.model_validate(_option_choice(table, _options(4)))


@pytest.mark.parametrize("count", [[1] * 19, [0] + [1] * 19, 0])
def test_choice_count_rejects_bad_tables(count):
    with pytest.raises(ValidationError):
        ChoiceDef.model_validate(_option_choice(count, _options(5)))


def test_option_requires_a_sibling_option():
    blade = _options(2, requires={"option": "o1"})
    assert ChoiceDef.model_validate(_option_choice(1, blade)).options[0].requires.option == "o1"
    for requires in [{"option": "missing"}, {"option": "o0"}]:
        with pytest.raises(ValidationError, match="isn't another option"):
            ChoiceDef.model_validate(_option_choice(1, _options(2, requires=requires)))
    with pytest.raises(ValidationError, match="requires needs a level or an option"):
        ChoiceDef.model_validate(_option_choice(1, _options(2, requires={})))


def _feature(spells: list[dict], uses: dict | None = None) -> dict:
    feature = {"slug": "f", "name": "F", "summary": "F.", "spells": spells}
    return feature | ({"uses": uses} if uses else {})


def test_free_cast_without_uses_is_at_will():
    at_will = {"spell": "mage-armor", "free_cast": True, "always_prepared": False}
    assert FeatureDef.model_validate(_feature([at_will])).uses is None
    with pytest.raises(ValidationError, match="don't spend charges"):
        FeatureDef.model_validate(_feature([at_will | {"charges": 2}]))
    with pytest.raises(ValidationError, match="must be cast free"):
        FeatureDef.model_validate(_feature([{"spell": "x", "always_prepared": False}]))
    with pytest.raises(ValidationError, match="can't cast spells free"):
        FeatureDef.model_validate(_feature([at_will]) | {"spends": {"feature": "charges"}})


@pytest.mark.parametrize(
    ("criteria", "ok"),
    [
        ({"level": 0}, True),  # any class's cantrips
        ({"level": 1, "ritual": True}, True),
        ({"max_level": 2}, False),  # a level range needs a class
        ({"class": "wizard", "level": 1, "ritual": False}, False),
    ],
)
def test_spell_choice_class_and_ritual_criteria(criteria, ok):
    choice = {"slug": "s", "name": "S", "kind": "spell", "criteria": criteria}
    if ok:
        ChoiceDef.model_validate(choice)
    else:
        with pytest.raises(ValidationError):
            ChoiceDef.model_validate(choice)


def test_class_slots_max_level_is_for_spell_choices_only():
    criteria = {"class": "warlock", "max_level": "class_slots"}
    choice = {"slug": "s", "name": "S", "kind": "spell", "criteria": criteria}
    ChoiceDef.model_validate(choice)
    with pytest.raises(ValidationError, match="for spell choices only"):
        ChoiceDef.model_validate(choice | {"kind": "spellbook"})


@pytest.mark.parametrize("action", ["action", "bonus_action", "reaction"])
def test_option_action_takes_feature_action_types(action):
    assert OptionDef.model_validate(_option([]) | {"action": action}).action == action


def test_option_action_rejects_other_values():
    with pytest.raises(ValidationError):
        OptionDef.model_validate(_option([]) | {"action": "free"})


@pytest.mark.parametrize("sheet", ["senses", "saves", "speed", "resistances", "traits"])
def test_sheet_placements(sheet):
    assert OptionDef.model_validate(_option([]) | {"sheet": sheet}).sheet == sheet
    assert FeatureDef.model_validate(_feature([]) | {"sheet": sheet}).sheet == sheet


def test_sheet_rejects_other_rows_and_feature_when_is_text():
    with pytest.raises(ValidationError):
        OptionDef.model_validate(_option([]) | {"sheet": "skills"})
    feature = FeatureDef.model_validate(_feature([]) | {"when": "When an enemy drops to 0 HP"})
    assert feature.when == "When an enemy drops to 0 HP"


def test_check_lists_what_shows_only_on_the_build_page(tmp_path, monkeypatch):
    pack = tmp_path / "notes"
    (pack / "species").mkdir(parents=True)
    (pack / "pack.yaml").write_text("slug: notes\nname: Notes\nkind: homebrew\nversion: 1\n")
    (pack / "species" / "folk.yaml").write_text(
        "slug: folk\nname: Folk\nsummary: Folk.\nfeatures:\n"
        "- {slug: untagged, name: Untagged, summary: A rule with no place on the sheet.}\n"
        "- {slug: on-purpose, name: On Purpose, summary: Build page only., sheet: none}\n"
        "- {slug: passive, name: Passive, summary: Always on., sheet: traits}\n"
        "- {slug: triggered, name: Triggered, summary: On a hit., when: When you hit}\n"
        "- {slug: tracked, name: Tracked, summary: Uses., uses: {max: 1, recharge: long_rest}}\n"
        "- slug: legacy\n  name: Legacy\n  summary: Pick one.\n  choices:\n"
        "  - slug: legacy\n    name: Legacy\n    kind: option\n    options:\n"
        "    - {slug: plain, name: Plain, summary: Nothing.}\n"
        "    - {slug: quiet, name: Quiet, summary: Nothing., sheet: none}\n"
        "    - {slug: fiery, name: Fiery, summary: Fire., grants: {resistances: [fire]}}\n"
    )
    monkeypatch.setattr(loader.settings, "content_paths", str(tmp_path))

    [found] = loader.discover()

    assert found.ok
    assert loader.build_page_only(found) == [
        "species/folk > untagged",
        "species/folk > legacy > legacy > plain",
    ]


def test_count_by_level_is_only_for_option_choices():
    subclass = {"slug": "sub", "name": "Sub", "kind": "subclass", "count": [1] * 20}
    with pytest.raises(ValidationError, match="count by level is for option choices"):
        ChoiceDef.model_validate(subclass)

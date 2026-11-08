import pytest
from sqlalchemy import select

from app.features.models import ChoiceOption
from app.sheet import service
from app.sheet.form import AcEffectForm
from app.sheet.models import CharacterAcEffect, CharacterHpEffect
from app.sheet.queries import (
    armor_class,
    damage_reactions,
    feature_uses,
    hp_effects,
    hp_view,
    spell_slots,
)
from app.spells.models import Spell


def _hp(db, character) -> tuple[int, int]:
    hp = hp_view(db, character)
    return hp.maximum, hp.current


def _stone(db) -> str:
    return str(db.scalar(select(ChoiceOption.id).where(ChoiceOption.slug == "stone")))


def _reaction_uses(db, character) -> int:
    [reaction] = damage_reactions(feature_uses(db, character))
    return reaction.uses.remaining


def _ac_effects(db, character) -> list[CharacterAcEffect]:
    return armor_class(db, character).effects


@pytest.fixture
def test_armor(db, character, prepare_from_book) -> Spell:
    armor = db.scalar(select(Spell).where(Spell.slug == "test-armor"))
    prepare_from_book(character, armor.id)
    return armor


def test_damage_and_healing(db, character):
    assert service.change_hp(db, character, "damage", "5", "") == ({}, None)
    assert _hp(db, character) == (8, 3)

    assert service.change_hp(db, character, "heal", "2", "") == ({}, None)
    assert _hp(db, character) == (8, 5)


@pytest.mark.parametrize(("action", "amount"), [("damage", "abc"), ("damage", "1000"), ("x", "3")])
def test_a_bad_hp_change_changes_nothing(db, character, action, amount):
    outcome = service.change_hp(db, character, action, amount, "")

    assert outcome == ({"hp": "Enter a whole number from 0 to 999."}, None)
    assert _hp(db, character) == (8, 8)


def test_damage_waits_on_a_reaction_unless_skipped(db, stone_giant):
    assert service.change_hp(db, stone_giant, "damage", "4", "") == ({}, 4)
    assert _hp(db, stone_giant) == (8, 8)

    assert service.change_hp(db, stone_giant, "damage", "4", "1") == ({}, None)
    assert _hp(db, stone_giant) == (8, 4)


def test_stones_endurance_reduces_the_damage_and_spends_a_use(db, stone_giant):
    uses = _reaction_uses(db, stone_giant)

    assert service.react_to_damage(db, stone_giant, "10", _stone(db), "5") == ({}, None)

    assert _hp(db, stone_giant) == (8, 5)
    assert _reaction_uses(db, stone_giant) == uses - 1


def test_a_bad_reaction_roll_reopens_the_prompt_and_changes_nothing(db, stone_giant):
    uses = _reaction_uses(db, stone_giant)

    outcome = service.react_to_damage(db, stone_giant, "10", _stone(db), "13")

    assert outcome == ({"reaction": "Enter your 1d12 roll, from 1 to 12."}, 10)
    assert _hp(db, stone_giant) == (8, 8)
    assert _reaction_uses(db, stone_giant) == uses


def test_an_unknown_reaction_changes_nothing(db, stone_giant):
    uses = _reaction_uses(db, stone_giant)

    outcome = service.react_to_damage(db, stone_giant, "10", "999999", "5")

    assert outcome == ({"hp": "That reaction isn't available right now."}, None)
    assert _hp(db, stone_giant) == (8, 8)
    assert _reaction_uses(db, stone_giant) == uses


def test_temporary_hit_points(db, character):
    assert service.change_temp_hp(db, character, "5", " False Life ") is None
    hp = hp_view(db, character)
    assert (hp.temp, hp.temp_source) == (5, "False Life")

    assert service.change_temp_hp(db, character, "x", "") == "Enter a whole number from 0 to 999."
    assert hp_view(db, character).temp == 5


def test_hp_effects_follow_the_rules(db, character):
    service.change_hp(db, character, "damage", "3", "")

    assert service.add_hp_effect(db, character, "Aid", "+5") is None
    assert _hp(db, character) == (13, 10)

    [aid] = hp_effects(db, character)
    service.end_hp_effect(db, character, aid)
    assert _hp(db, character) == (8, 8)

    assert service.add_hp_effect(db, character, "Drain", "-6") is None
    assert _hp(db, character) == (2, 2)


@pytest.mark.parametrize(("label", "delta"), [("", "5"), ("Aid", "0"), ("Aid", "abc")])
def test_a_bad_hp_effect_changes_nothing(db, character, label, delta):
    error = service.add_hp_effect(db, character, label, delta)

    assert error == "Give the effect a name and a non-zero amount (e.g. Aid, +5)."
    assert hp_effects(db, character) == []


@pytest.mark.parametrize(
    ("kind", "value", "stored"),
    [("base", "13", ("base", 13)), ("minimum", "17", ("minimum", 17)), ("x", "+2", ("bonus", 2))],
)
def test_ac_effects(db, character, kind, value, stored):
    form = AcEffectForm(label="Effect", kind=kind, value=value)

    assert service.add_ac_effect(db, character, form) is None

    [effect] = _ac_effects(db, character)
    assert (effect.kind, effect.value) == stored
    service.end_ac_effect(db, effect)
    db.flush()
    assert _ac_effects(db, character) == []


@pytest.mark.parametrize(
    ("label", "kind", "value", "error"),
    [
        ("", "base", "13", "a base AC from 10 to 30 (e.g. Mage Armor, 13)"),
        ("Mage Armor", "base", "9", "a base AC from 10 to 30 (e.g. Mage Armor, 13)"),
        ("Barkskin", "minimum", "31", "a minimum AC from 10 to 30 (e.g. Barkskin, 17)"),
        ("Shield of Faith", "bonus", "0", "a non-zero bonus (e.g. Shield of Faith, +2)"),
    ],
)
def test_a_bad_ac_effect_changes_nothing(db, character, label, kind, value, error):
    form = AcEffectForm(label=label, kind=kind, value=value)

    assert service.add_ac_effect(db, character, form) == f"Give the effect a name and {error}."
    assert _ac_effects(db, character) == []


def test_casting_an_ac_spell_spends_the_slot_and_applies_it(db, character, test_armor):
    assert service.cast_ac_spell(db, character, str(test_armor.id), "1") is None

    assert spell_slots(db, character)[1].remaining == 1
    assert armor_class(db, character).base == 13


def test_a_bad_ac_cast_changes_nothing(db, character, test_armor):
    error = service.cast_ac_spell(db, character, "999999", "1")
    assert error == "Only spells that change your AC can be cast here."
    service.set_slots_remaining(db, character, 1, 0)

    assert service.cast_ac_spell(db, character, str(test_armor.id), "1") == (
        "You have no level 1 slots left."
    )
    assert _ac_effects(db, character) == []


def test_an_ac_spell_without_an_at_will_feature_isnt_cast_at_will(db, character, test_armor):
    error = service.cast_ac_spell(db, character, str(test_armor.id), "at_will")

    assert error == "Test Armor isn't cast at will."
    assert _ac_effects(db, character) == []
    assert spell_slots(db, character)[1].remaining == 2


def test_someone_elses_rows_are_not_found(client, db, character, theirs):
    their_hp = CharacterHpEffect(character_id=theirs.id, label="Aid", max_hp_delta=5)
    their_ac = CharacterAcEffect(character_id=theirs.id, label="Mage Armor", kind="base", value=13)
    db.add_all([their_hp, their_ac])
    db.commit()

    mine = f"/characters/{character.id}/sheet"
    assert client.post(f"{mine}/hp-effects/{their_hp.id}/end").status_code == 404
    assert client.post(f"{mine}/ac-effects/{their_ac.id}/end").status_code == 404
    for path in ("hp", "hp/react", "temp-hp", "hp-effects", "ac-effects", "ac-effects/cast"):
        assert client.post(f"/characters/{theirs.id}/sheet/{path}").status_code == 404
    assert hp_effects(db, theirs) == [their_hp]


def test_damage_through_the_app(client, character):
    url = f"/characters/{character.id}/sheet/hp"

    response = client.post(url, data={"action": "damage", "amount": "x"})
    assert response.status_code == 400 and "Enter a whole number from 0 to 999." in response.text

    response = client.post(url, data={"action": "damage", "amount": "3"})
    assert response.headers["HX-Retarget"] == "#sheet-page"

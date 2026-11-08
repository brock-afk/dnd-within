import pytest

from app.features.models import Feature
from app.sheet import service
from app.sheet.form import RecoveryForm
from app.sheet.models import CharacterFeatureUse, CharacterHpEffect
from app.sheet.queries import feature_uses, hit_dice, hp_view, spell_slots
from app.sheet.service import long_rest, play_state


def test_long_rest_ends_max_hp_effects_and_restores_hp(db, character):
    db.add_all(
        [
            CharacterHpEffect(character_id=character.id, label="Wight drain", max_hp_delta=-3),
            CharacterHpEffect(character_id=character.id, label="Aid", max_hp_delta=5),
        ]
    )
    play_state(db, character).current_hp = 2
    db.flush()
    assert hp_view(db, character).maximum == 10

    long_rest(db, character)
    db.flush()

    hp = hp_view(db, character)
    assert hp.effects == []
    assert (hp.current, hp.maximum) == (8, 8)


@pytest.fixture
def wand(db, charged_item):

    def wand(character, regain, expended, attuned=True) -> Feature:
        uses = {"max": 7, "recharge": "dawn", "regain": regain}
        charges = charged_item(character, uses, attuned)
        db.add(
            CharacterFeatureUse(character_id=character.id, feature_id=charges.id, expended=expended)
        )
        db.flush()
        return charges

    return wand


def _expended_after_long_rest(db, character, charges) -> int | None:
    long_rest(db, character)
    db.flush()
    row = db.get(CharacterFeatureUse, (character.id, charges.id))
    return row.expended if row else None


@pytest.mark.parametrize("attuned", [True, False])
def test_long_rest_rolls_regain_attuned_or_not(db, character, wand, attuned):
    charges = wand(character, "1d1+1", expended=6, attuned=attuned)
    assert _expended_after_long_rest(db, character, charges) == 4


def test_long_rest_never_spends_charges(db, character, wand):
    charges = wand(character, "1d1-2", expended=2)
    assert _expended_after_long_rest(db, character, charges) == 2


def _hit_die(db, character) -> tuple[str, int]:
    [dice] = hit_dice(db, character)
    return str(dice.character_class.id), dice.available


def test_a_hit_die_heals_by_the_roll_and_constitution(db, character):
    class_id, _ = _hit_die(db, character)
    service.change_hp(db, character, "damage", "6", "")

    assert service.spend_hit_die(db, character, class_id, "3") is None

    assert hp_view(db, character).current == 7
    assert _hit_die(db, character) == (class_id, 0)
    error = service.spend_hit_die(db, character, class_id, "3")
    assert error == "You have no hit dice left. They come back on a long rest."


@pytest.mark.parametrize("roll", ["7", "x", ""])
def test_a_bad_hit_die_roll_changes_nothing(db, character, roll):
    class_id, _ = _hit_die(db, character)
    service.change_hp(db, character, "damage", "6", "")

    error = service.spend_hit_die(db, character, class_id, roll)

    assert error == "Enter your d6 roll, from 1 to 6."
    assert hp_view(db, character).current == 2
    assert _hit_die(db, character) == (class_id, 1)


def _recovery(db, character):
    return next(u for u in feature_uses(db, character) if u.feature.slug == "arcane-recovery")


def _state(db, character) -> tuple[int, int]:
    return spell_slots(db, character)[1].remaining, _recovery(db, character).remaining


def test_arcane_recovery_recovers_a_slot(db, character):
    assert service.change_slots(db, character, 1, "0") is None

    form = RecoveryForm(level_1=" 1 ")
    assert service.recover_slots(db, character, _recovery(db, character), form) is None

    assert _state(db, character) == (1, 0)
    form = RecoveryForm(level_1="2")
    error = service.recover_slots(db, character, _recovery(db, character), form)
    assert error == "Arcane Recovery is used. It comes back on a long rest."
    assert _state(db, character) == (1, 0)


@pytest.mark.parametrize(
    ("spent", "count", "error"),
    [
        (2, "", "Choose at least one slot to recover."),
        (2, "x", "Enter how many slots of each level to recover."),
        (0, "1", "You only have 0 level 1 slots spent."),
        (2, "2", "Arcane Recovery recovers at most 1 total slot levels."),
    ],
)
def test_a_bad_recovery_changes_nothing(db, character, spent, count, error):
    assert service.change_slots(db, character, 1, str(2 - spent)) is None

    form = RecoveryForm(level_1=count)
    assert service.recover_slots(db, character, _recovery(db, character), form) == error

    assert _state(db, character) == (2 - spent, 1)


def test_someone_elses_rests_are_not_found(client, theirs):
    sheet = f"/characters/{theirs.id}/sheet"
    assert client.get(f"{sheet}/short-rest").status_code == 404
    for path in (
        "uses/1",
        "features/1/use",
        "short-rest/hit-die",
        "short-rest/recover/1",
        "short-rest/finish",
        "long-rest",
    ):
        assert client.post(f"{sheet}/{path}").status_code == 404


def test_rests_through_the_app(client, db, character):
    sheet = f"/characters/{character.id}/sheet"
    class_id, _ = _hit_die(db, character)
    assert "Spend a hit die" in client.get(f"{sheet}/short-rest").text

    response = client.post(f"{sheet}/short-rest/hit-die", data={"class_id": class_id, "roll": "9"})
    assert response.status_code == 400 and "Enter your d6 roll, from 1 to 6." in response.text

    for path in ("short-rest/finish", "long-rest"):
        response = client.post(f"{sheet}/{path}")
        assert response.status_code == 200 and response.headers["HX-Retarget"] == "#sheet-page"

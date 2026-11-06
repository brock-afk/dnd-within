import pytest
from sqlalchemy import select

from app.features.kinds import KINDS
from app.features.models import Choice
from app.leveling import service
from app.leveling.queries import level_up_view
from app.sheet.service import hp_view, play_state


def _up(db, character, method: str, roll: str = "") -> str | None:
    """Level up from a page showing the current level."""
    return service.level_up(db, character, str(character.level), method, roll)


def _down(db, character) -> str | None:
    return service.level_down(db, character, str(character.level))


def test_levelling_up_raises_max_and_current_hp(db, character):
    play_state(db, character).current_hp = 5

    assert _up(db, character, "fixed") is None

    assert character.level == 2
    hp = hp_view(db, character)
    assert (hp.maximum, hp.current) == (14, 11)  # + d6 fixed 4 + 2 CON


def test_a_roll_sets_the_new_levels_hit_points(db, character):
    assert _up(db, character, "rolled", " 5 ") is None

    assert character.levels[-1].hp_roll == 5
    assert hp_view(db, character).maximum == 15


@pytest.mark.parametrize(
    "method, roll, error",
    [
        ("max", "", "Choose the fixed value or enter a roll."),
        ("rolled", "", "Enter your d6 roll, from 1 to 6."),
        ("rolled", "0", "Enter your d6 roll, from 1 to 6."),
        ("rolled", "7", "Enter your d6 roll, from 1 to 6."),
    ],
)
def test_an_invalid_level_up_changes_nothing(db, character, method, roll, error):
    assert _up(db, character, method, roll) == error

    assert character.level == 1
    assert hp_view(db, character).maximum == 8


def test_levelling_up_needs_ability_scores(db, character):
    character.ability_method = None

    assert _up(db, character, "fixed") == (
        "Set ability scores first: hit points depend on Constitution."
    )
    assert character.level == 1
    assert level_up_view(db, character).con_mod is None


def test_level_20_is_the_last(db, character, level_up):
    level_up(character, 20)

    assert _up(db, character, "fixed") == "Level 20 is the maximum."
    assert character.level == 20
    assert level_up_view(db, character).at_max


def test_levelling_down_removes_the_levels_picks_and_hit_points(db, character, level_up):
    level_up(character, 2)
    increase = db.scalar(select(Choice).where(Choice.slug == "test-increase"))
    kind = KINDS["ability_scores"]
    assert kind.save(db, increase, character.id, ["CON2.STR1"]) is None
    assert hp_view(db, character).maximum == 16  # CON 16: d6 + 3, then 4 + 3

    assert _down(db, character) is None

    assert character.level == 1
    assert kind.picked_amounts(db, increase, character.id) == {}
    hp = hp_view(db, character)
    assert (hp.maximum, hp.current) == (8, 8)


@pytest.mark.parametrize("shown", ["1", "3", "", "²"])
def test_a_stale_page_changes_nothing(db, character, level_up, shown):
    level_up(character, 2)

    assert service.level_up(db, character, shown, "fixed", "") == service.STALE
    assert service.level_down(db, character, shown) == service.STALE
    assert character.level == 2


def test_level_1_cant_be_removed(db, character):
    assert _down(db, character) == "Level 1 can't be removed."

    assert character.level == 1


def test_someone_elses_character_is_not_found(client, theirs):
    assert client.get(f"/characters/{theirs.id}/level-up").status_code == 404
    response = client.post(f"/characters/{theirs.id}/level-up", data={"hp_method": "fixed"})
    assert response.status_code == 404
    assert client.post(f"/characters/{theirs.id}/level-down").status_code == 404


def test_level_up_and_down_through_the_app(client, db, character):
    url = f"/characters/{character.id}"
    response = client.get(f"{url}/level-up")
    assert response.status_code == 200 and "Level 2 Wizard" in response.text

    bad_roll = {"level": "1", "hp_method": "rolled", "hp_roll": "9"}
    response = client.post(f"{url}/level-up", data=bad_roll)
    assert response.status_code == 400
    assert "Enter your d6 roll, from 1 to 6." in response.text and 'value="9"' in response.text

    response = client.post(f"{url}/level-up", data=bad_roll | {"hp_roll": "3"})
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#character-page"
    assert character.level == 2

    response = client.post(f"{url}/level-down", data={"level": "2"})
    assert response.status_code == 200
    assert character.level == 1

    response = client.post(f"{url}/level-down", data={"level": "2"})  # from a stale page
    assert response.headers["HX-Retarget"] == "#character-page"
    assert character.level == 1

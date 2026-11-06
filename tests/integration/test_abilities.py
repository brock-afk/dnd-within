import pytest
from sqlalchemy import select

from app.abilities import service
from app.abilities.form import AbilityForm, IncreaseForm
from app.features.kinds import KINDS
from app.features.models import Choice, Feature
from app.sheet.service import hp_view, play_state

STANDARD = dict(
    strength="8", dexterity="14", constitution="15", intelligence="10", wisdom="12", charisma="13"
)


def _picked(db, choice, character) -> dict[str, int]:
    return KINDS["ability_scores"].picked_amounts(db, choice, character.id)


def _manual(constitution: int) -> AbilityForm:
    """Manual entry with every other score at 10."""
    rolls = [str(constitution)] + ["10"] * 5
    scores = dict.fromkeys(STANDARD, "10") | {"constitution": str(constitution)}
    return AbilityForm(method="manual", rolls=rolls, **scores)


def test_saving_a_standard_array(db, character):
    form = AbilityForm(method="standard_array", **STANDARD)

    assert service.save_scores(db, character, form) == {}

    assert character.ability_method == "standard_array"
    assert (character.strength, character.constitution) == (8, 15)


def test_a_constitution_change_moves_hit_points(db, character):
    play_state(db, character).current_hp = 5

    assert service.save_scores(db, character, _manual(18)) == {}  # +2 CON modifier
    hp = hp_view(db, character)
    assert (hp.maximum, hp.current) == (10, 7)

    assert service.save_scores(db, character, _manual(8)) == {}  # −1
    hp = hp_view(db, character)
    assert (hp.maximum, hp.current) == (5, 5)


@pytest.mark.parametrize(
    "form",
    [
        AbilityForm(method="", **STANDARD),
        AbilityForm(method="standard_array", **dict.fromkeys(STANDARD, "15")),
        AbilityForm(method="point_buy", **dict.fromkeys(STANDARD, "15")),
        AbilityForm(method="manual", rolls=["10"] * 5, **dict.fromkeys(STANDARD, "10")),
    ],
    ids=["no method", "repeated value", "over budget", "missing roll"],
)
def test_an_invalid_set_changes_nothing(db, character, form):
    assert service.save_scores(db, character, form)

    assert (character.ability_method, character.constitution) == ("manual", 14)
    assert hp_view(db, character).maximum == 8


@pytest.mark.parametrize(
    ("form", "amounts", "hp"),
    [
        (IncreaseForm(plus2="CON", plus1="STR"), {"CON": 2, "STR": 1}, (9, 6)),  # CON 16
        (IncreaseForm(split="even"), {"STR": 1, "DEX": 1, "CON": 1}, (8, 5)),  # CON 15
    ],
)
def test_saving_an_increase(db, character, increase, form, amounts, hp):
    play_state(db, character).current_hp = 5

    assert service.save_increase(db, character, increase, form) is None

    assert _picked(db, increase, character) == amounts
    view = hp_view(db, character)
    assert (view.maximum, view.current) == hp


def test_a_half_made_increase_saves_nothing(db, character, increase):
    error = service.save_increase(db, character, increase, IncreaseForm(plus2="CON"))

    assert error == "Choose where the +2 and the +1 go."
    assert _picked(db, increase, character) == {}


def test_someone_elses_character_is_not_found(client, theirs, increase):
    url = f"/characters/{theirs.id}"

    assert client.get(f"{url}/abilities/edit").status_code == 404
    assert client.post(f"{url}/abilities", data=STANDARD).status_code == 404
    assert client.post(f"{url}/ability-increases/{increase.id}").status_code == 404
    assert client.post(f"{url}/ability-increases/{increase.id}/preview").status_code == 404


def test_only_the_characters_own_increases_are_found(client, db, character, wanderer):
    skills = db.scalar(select(Choice).where(Choice.kind == "skill"))  # not an increase
    unchosen = db.scalar(select(Choice).join(Feature).where(Feature.background_id == wanderer.id))
    url = f"/characters/{character.id}/ability-increases"

    for choice in (skills, unchosen):
        assert client.post(f"{url}/{choice.id}/preview").status_code == 404
        assert client.post(f"{url}/{choice.id}", data={"plus2": "CON"}).status_code == 404


def test_editing_scores_through_the_app(client, db, character):
    url = f"/characters/{character.id}/abilities"
    for method in ("standard_array", "point_buy", "manual", "unknown"):
        assert client.get(f"{url}/edit", params={"method": method}).status_code == 200

    step = {"method": "point_buy", "step": "strength:1"}
    assert "Points left: <strong>26</strong>" in client.post(f"{url}/preview", data=step).text

    bad = {"method": "standard_array"} | STANDARD | {"strength": "²"}
    response = client.post(url, data=bad)
    assert response.status_code == 400 and "Choose a score." in response.text

    response = client.post(url, data={"method": "standard_array"} | STANDARD)
    assert response.headers["HX-Retarget"] == "#character-page"
    assert character.constitution == 15


def test_an_increase_through_the_app(client, db, character, increase):
    url = f"/characters/{character.id}/ability-increases/{increase.id}"
    assert f'hx-get="{url}"' in client.get(f"/characters/{character.id}").text  # its Choose button
    response = client.get(url)
    assert response.status_code == 200 and f"increase-editor-{increase.id}" in response.text

    clash = {"plus2": "CON", "plus1": "CON", "changed": "plus1"}
    assert client.post(f"{url}/preview", data=clash).status_code == 200

    assert client.post(url, data={"plus2": "CON"}).status_code == 400
    response = client.post(url, data={"plus2": "CON", "plus1": "DEX"})
    assert response.headers["HX-Retarget"] == "#character-page"
    assert _picked(db, increase, character) == {"CON": 2, "DEX": 1}

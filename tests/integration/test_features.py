from datetime import datetime

import pytest
from sqlalchemy import select

from app.features import service
from app.features.kinds import KINDS
from app.features.models import Choice
from app.features.queries import choice_form_view
from app.skills.models import Skill


@pytest.fixture
def skills(wizard_choice) -> Choice:
    """The test wizard's two skill proficiencies, from Arcana, History, Insight, …"""
    return wizard_choice("skills")


def _key(db, slug: str) -> str:
    return str(db.scalar(select(Skill.id).where(Skill.slug == slug)))


def _picked(db, choice, character) -> list[str]:
    return sorted(o.name for o in KINDS[choice.kind].picked(db, choice, character.id))


def test_saving_picks(db, character, skills):
    keys = [_key(db, "arcana"), _key(db, "history")]

    assert service.save_choice(db, character, skills, keys) is None

    assert _picked(db, skills, character) == ["Arcana", "History"]
    assert choice_form_view(db, character, skills).selected == keys


@pytest.mark.parametrize(
    ("skills_picked", "unknown", "error"),
    [
        (["arcana"], [], "Choose exactly 2. You picked 1."),
        (["arcana", "arcana"], [], "Choose exactly 2. You picked 1."),  # a repeat counts once
        (["arcana", "insight", "medicine"], [], "Choose exactly 2. You picked 3."),
        (["arcana"], ["999999"], "That isn't one of the options."),
    ],
)
def test_an_invalid_pick_changes_nothing(db, character, skills, skills_picked, unknown, error):
    service.save_choice(db, character, skills, [_key(db, "nature"), _key(db, "religion")])
    keys = [_key(db, s) for s in skills_picked] + unknown

    assert service.save_choice(db, character, skills, keys) == error

    assert _picked(db, skills, character) == ["Nature", "Religion"]


def test_only_the_characters_own_grid_choices_are_found(
    client, db, character, theirs, skills, wizard_choice, increase
):
    scholar = wizard_choice("scholar")  # a level 2 feature's: not had at level 1

    for url in (
        f"/characters/{theirs.id}/choices/{skills.id}",
        f"/characters/{character.id}/choices/{scholar.id}",
        f"/characters/{character.id}/choices/{increase.id}",  # has its own editor
    ):
        assert client.get(url).status_code == 404
        assert client.post(url, data={"picks": [_key(db, "arcana")]}).status_code == 404


def test_choosing_through_the_app(client, db, character, skills):
    url = f"/characters/{character.id}/choices/{skills.id}"
    assert f'hx-get="{url}"' in client.get(f"/characters/{character.id}").text  # its Choose button
    assert "Choose 2" in client.get(url).text

    response = client.post(url, data={"picks": [_key(db, "arcana")]})
    assert response.status_code == 400 and "Choose exactly 2. You picked 1." in response.text

    response = client.post(url, data={"picks": [_key(db, "arcana"), _key(db, "history")]})
    assert response.headers["HX-Retarget"] == "#character-page"
    assert _picked(db, skills, character) == ["Arcana", "History"]


@pytest.mark.parametrize("retired", ["choice", "feature"])
def test_a_retired_choice_cant_be_opened_or_changed(client, db, character, skills, retired):
    keys = [_key(db, "arcana"), _key(db, "history")]
    service.save_choice(db, character, skills, keys)
    (skills if retired == "choice" else skills.feature).retired_at = datetime.now()
    db.commit()  # a 404 rolls the request back; committing keeps the setup (see `theirs`)
    url = f"/characters/{character.id}/choices/{skills.id}"

    assert client.get(url).status_code == 404
    assert client.post(url, data={"picks": keys}).status_code == 404

    service.remove_inapplicable_picks(db, character)
    assert _picked(db, skills, character) == ["Arcana", "History"]  # picks made before stay


def test_a_retired_increase_cant_be_opened_or_changed(client, db, character, increase):
    increase.retired_at = datetime.now()
    db.commit()  # a 404 rolls the request back; committing keeps the setup (see `theirs`)
    url = f"/characters/{character.id}/ability-increases/{increase.id}"

    assert client.get(url).status_code == 404
    assert client.post(url, data={"plus2": "CON", "plus1": "STR"}).status_code == 404

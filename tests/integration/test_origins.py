from datetime import datetime

import pytest
from sqlalchemy import select

from app.backgrounds.models import Background
from app.characters.origins import BACKGROUND, SPECIES
from app.characters.queries import origin_form_view
from app.characters.service import choose_origin
from app.features.kinds import KINDS
from app.features.models import CharacterChoicePick
from app.species.models import Species


def _picks(db, character) -> list[CharacterChoicePick]:
    query = select(CharacterChoicePick).where(CharacterChoicePick.character_id == character.id)
    return list(db.scalars(query))


def test_switching_backgrounds_drops_the_old_ones_picks(db, character, increase):
    scholar = db.scalar(select(Background).where(Background.slug == "test-scholar"))
    kind = KINDS["ability_scores"]
    assert kind.save(db, increase, character.id, ["STR2.DEX1"]) is None

    assert choose_origin(db, character, BACKGROUND, str(scholar.id)) is None

    assert character.background_id == scholar.id
    assert kind.picked_amounts(db, increase, character.id) == {}


@pytest.mark.parametrize("key", ["", "abc", "999999", "²", "1" * 5000])
def test_an_unknown_background_changes_nothing(db, character, key):
    assert choose_origin(db, character, BACKGROUND, key) == "Choose a background."

    assert character.background_id is None


def test_a_retired_background_cant_be_chosen(db, character, wanderer):
    wanderer.retired_at = datetime.now()
    db.flush()

    assert choose_origin(db, character, BACKGROUND, str(wanderer.id)) == "Choose a background."
    assert character.background_id is None
    assert wanderer.name not in [
        o.name for o in origin_form_view(db, character, BACKGROUND).options
    ]


def test_re_saving_a_retired_current_pick_is_allowed(db, character, wanderer):
    choose_origin(db, character, BACKGROUND, str(wanderer.id))
    wanderer.retired_at = datetime.now()
    db.flush()

    assert choose_origin(db, character, BACKGROUND, str(wanderer.id)) is None
    assert character.background_id == wanderer.id


def test_switching_species_drops_the_old_ones_picks(db, stone_giant):
    assert _picks(db, stone_giant)
    legacy_folk = db.scalar(select(Species).where(Species.slug == "legacy-folk"))

    assert choose_origin(db, stone_giant, SPECIES, str(legacy_folk.id)) is None

    assert stone_giant.species_id == legacy_folk.id
    assert _picks(db, stone_giant) == []


def test_choosing_the_current_species_keeps_its_picks(db, stone_giant):
    assert choose_origin(db, stone_giant, SPECIES, str(stone_giant.species_id)) is None

    assert _picks(db, stone_giant)


def test_the_form_shows_the_current_pick_unless_one_was_submitted(db, character):
    view = origin_form_view(db, character, SPECIES)

    assert view.selected == str(character.species_id)
    assert origin_form_view(db, character, SPECIES, selected="abc").selected == "abc"


def test_someone_elses_character_is_not_found(client, theirs, wanderer):
    url = f"/characters/{theirs.id}/background"

    assert client.get(url).status_code == 404
    assert client.post(url, data={"background_id": wanderer.id}).status_code == 404


def test_picking_a_background_through_the_app(client, db, character, wanderer):
    url = f"/characters/{character.id}/background"

    form = client.get(url).text
    assert "Test Wanderer" in form and "Origin feat: Test Origin Feat" in form

    response = client.post(url, data={"background_id": "abc"})
    assert response.status_code == 400 and "Choose a background." in response.text
    assert "removes the picks" not in response.text

    response = client.post(url, data={"background_id": wanderer.id})
    assert response.headers["HX-Retarget"] == "#character-page"
    db.refresh(character)
    assert character.background_id == wanderer.id


def test_switching_species_through_the_app(client, db, character):
    legacy_folk = db.scalar(select(Species).where(Species.slug == "legacy-folk"))
    url = f"/characters/{character.id}/species"

    assert "Speed " in client.get(url).text

    response = client.post(url, data={"species_id": legacy_folk.id})
    assert response.headers["HX-Retarget"] == "#character-page"
    db.refresh(character)
    assert character.species_id == legacy_folk.id

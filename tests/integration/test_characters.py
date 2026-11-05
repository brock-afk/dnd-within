import pytest
from sqlalchemy import func, select, update

from app.characters.form import CharacterForm
from app.characters.models import Character
from app.characters.queries import build_page_view, character_list_view, refreshed_build_view
from app.characters.service import create_character, delete_character, rename


@pytest.fixture
def form(character) -> CharacterForm:
    """The test character's class and species."""
    return CharacterForm(
        name="  New Hero  ",
        class_id=character.classes[0].class_id,
        species_id=character.species_id,
    )


def _count(db) -> int:
    return db.scalar(select(func.count()).select_from(Character))


def test_creating_starts_at_level_one_in_the_class(db, owner, form):
    character, errors = create_character(db, owner, form)

    assert errors == {}
    assert character.name == "New Hero"
    assert character.level == 1 and character.classes[0].class_id == form.class_id


def test_an_invalid_character_saves_nothing(db, owner, form):
    before = _count(db)

    character, errors = create_character(db, owner, form.model_copy(update={"name": ""}))
    assert character is None and set(errors) == {"name"}
    _, errors = create_character(db, owner, form.model_copy(update={"class_id": None}))
    assert set(errors) == {"class_id"}

    assert _count(db) == before


def test_rename_and_delete_errors_change_nothing(db, character):
    assert rename(character, "") == "Give your character a name."
    assert rename(character, "x" * 61) is not None
    assert character.name == "Test"

    assert delete_character(db, character, "nope") == "Type delete to confirm."
    assert db.get(Character, character.id) is not None


def test_list_opens_unbuilt_characters_on_the_build_page(db, owner, character):
    # The fixture character has no background yet.
    view = character_list_view(db, owner)

    assert view.characters == [character]
    assert view.links == {character.id: f"/characters/{character.id}"}


def test_the_refreshed_view_shows_changes_made_since_loading(db, owner, character):
    build_page_view(db, owner, character)
    # Changed in the database, not on the loaded object, like a relationship's row.
    db.execute(
        update(Character).where(Character.id == character.id).values(name="Renamed"),
        execution_options={"synchronize_session": False},
    )

    assert build_page_view(db, owner, character).character.name == "Test"
    assert refreshed_build_view(db, owner, character).character.name == "Renamed"


def test_someone_elses_character_is_not_found(client, db, other_user, form):
    theirs, _ = create_character(db, other_user, form.model_copy(update={"name": "Theirs"}))
    # A 404 rolls back the request's changes; on the shared test session that would take the
    # setup with it. Committing only releases a savepoint: the test still rolls back at the end.
    db.commit()

    assert client.get(f"/characters/{theirs.id}").status_code == 404
    assert client.post(f"/characters/{theirs.id}/name", data={"name": "Mine"}).status_code == 404
    assert (
        client.post(f"/characters/{theirs.id}/delete", data={"confirm": "delete"}).status_code
        == 404
    )
    db.expire_all()
    assert db.get(Character, theirs.id).name == "Theirs"


def test_create_rename_and_delete_through_the_app(client, db, form):
    data = form.model_dump()

    response = client.post("/characters", data=data | {"name": ""})
    assert response.status_code == 400 and "Give your character a name." in response.text

    response = client.post("/characters", data=data)
    character_id = int(response.headers["HX-Redirect"].rsplit("/", 1)[1])
    assert "New Hero" in client.get(f"/characters/{character_id}").text
    assert f'href="/characters/{character_id}"' in client.get("/characters").text

    response = client.post(f"/characters/{character_id}/name", data={"name": " "})
    assert response.status_code == 400
    response = client.post(f"/characters/{character_id}/name", data={"name": "Renamed"})
    assert "<h1>Renamed</h1>" in response.text

    response = client.post(f"/characters/{character_id}/delete", data={"confirm": "Delete"})
    assert response.headers["HX-Redirect"] == "/characters"
    assert db.get(Character, character_id) is None

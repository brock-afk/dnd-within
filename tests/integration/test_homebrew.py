import pytest
from sqlalchemy import select

from app.auth.models import User
from app.homebrew.form import ItemForm
from app.homebrew.queries import library_view, new_item_view
from app.homebrew.service import save_from_form
from app.inventory.models import CharacterItem, Item


def _ring(**fields) -> ItemForm:
    return ItemForm(
        **{"name": "Test Ring", "rarity": "common", "summary": "A ring for tests."} | fields
    )


@pytest.fixture
def owner(db, character) -> User:
    return db.get(User, character.user_id)


@pytest.fixture
def other_user(db) -> User:
    user = User(username="someone-else", password_hash="x")
    db.add(user)
    db.flush()
    return user


def test_saving_adds_the_item_to_the_character_it_was_opened_from(db, owner, character):
    assert save_from_form(db, owner, _ring(), None, character) == {}

    [(item, _)] = library_view(db, owner).items
    assert item.name == "Test Ring"
    carried = db.scalar(select(CharacterItem).where(CharacterItem.character_id == character.id))
    assert carried.item_id == item.id


def test_an_invalid_form_saves_nothing(db, owner, character):
    errors = save_from_form(db, owner, _ring(name=""), None, character)

    assert "name" in errors
    assert library_view(db, owner).items == []
    assert (
        db.scalar(select(CharacterItem).where(CharacterItem.character_id == character.id)) is None
    )


def test_editing_keeps_the_same_item(db, owner):
    save_from_form(db, owner, _ring(), None, None)
    [(item, _)] = library_view(db, owner).items

    assert save_from_form(db, owner, _ring(name="Renamed Ring"), item, None) == {}

    assert [i.name for i, _ in library_view(db, owner).items] == ["Renamed Ring"]
    assert library_view(db, owner).items[0][0].id == item.id


def test_new_item_drops_someone_elses_character(db, character, other_user):
    view = new_item_view(db, other_user, str(character.id))

    assert view.character is None and view.form.character == ""


def test_someone_elses_item_is_not_found(client, db, other_user):
    save_from_form(db, other_user, _ring(), None, None)
    [(item, _)] = library_view(db, other_user).items
    # A 404 rolls back the request's changes; on the shared test session that would take the
    # setup with it. Committing only releases a savepoint: the test still rolls back at the end.
    db.commit()

    assert client.get(f"/homebrew/items/{item.id}/edit").status_code == 404
    assert client.post(f"/homebrew/items/{item.id}/delete").status_code == 404
    assert db.get(Item, item.id).retired_at is None


def test_create_edit_and_delete_through_the_app(client, db, owner):
    form = {"name": "Test Ring", "rarity": "common", "summary": "A ring for tests."}

    response = client.post("/homebrew/items", data=form | {"name": ""})
    assert response.status_code == 400
    assert "Give the item a name" in response.text

    response = client.post("/homebrew/items", data=form)
    assert response.headers["HX-Redirect"] == "/homebrew"
    [(item, _)] = library_view(db, owner).items
    assert "Test Ring" in client.get("/homebrew").text
    assert 'value="Test Ring"' in client.get(f"/homebrew/items/{item.id}/edit").text

    response = client.post(f"/homebrew/items/{item.id}/delete")
    assert response.headers["HX-Redirect"] == "/homebrew"
    assert library_view(db, owner).items == []


def test_editor_rows_cancel_link_and_delete_confirm(client, db, owner, character):
    form = {"name": "Test Ring", "rarity": "common", "summary": "A ring for tests."}
    sheet = f"/characters/{character.id}/sheet"

    page = client.get("/homebrew/items/new", params={"character": character.id}).text
    assert f'href="{sheet}"' in page  # Cancel goes back to the sheet it was opened from

    preview = client.post("/homebrew/items/preview", data=form | {"add_row": "ability"})
    assert preview.status_code == 200 and preview.text.count('name="ability_name"') == 1
    assert 'value="Test Ring"' in preview.text  # what was typed is kept

    response = client.post("/homebrew/items", data=form | {"character": character.id})
    assert response.headers["HX-Redirect"] == sheet
    [(item, _)] = library_view(db, owner).items
    confirm = client.get(f"/homebrew/items/{item.id}/delete")
    assert "Delete Test Ring?" in confirm.text

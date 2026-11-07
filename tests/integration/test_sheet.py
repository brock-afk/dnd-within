from sqlalchemy import select, update

from app.characters.models import Character
from app.sharing.service import make_link
from app.sheet.queries import CopyPanel, copy_confirmation, refreshed_sheet_view, sheet_view
from app.spells.models import Spell


def test_modes_fill_only_their_own_parts(db, owner, stone_giant):
    view = sheet_view(db, owner, stone_giant)
    assert (view.hit_dice, view.recoveries, view.reactions) == ([], [], [])
    assert view.copy is None

    assert sheet_view(db, owner, stone_giant, resting=True).hit_dice
    # Stone's Endurance, offered before the damage lands.
    assert sheet_view(db, owner, stone_giant, pending_damage=5).reactions


def test_the_copy_panel_shows_its_search_or_its_confirm_step(db, owner, character):
    spell = db.scalar(select(Spell).where(Spell.level == 1).limit(1))

    search = sheet_view(db, owner, character, copying=CopyPanel(query=" fire "))
    assert search.copy["query"] == "fire"

    confirm = copy_confirmation(db, character, spell, "fire")
    assert (confirm["spell"], confirm["cost"]) == (spell, "2 hours and 50 GP")


def test_the_shared_view_links_within_the_share_and_hides_it(db, owner, character):
    make_link(db, character)

    assert sheet_view(db, owner, character).share is not None
    shared = sheet_view(db, None, character, read_only=True, base_url="/shared/abc")
    assert (shared.share, shared.base_url) == (None, "/shared/abc")


def test_the_refreshed_view_shows_changes_made_since_loading(db, owner, character):
    sheet_view(db, owner, character)
    # Changed in the database, not on the loaded object, like a relationship's row.
    db.execute(
        update(Character).where(Character.id == character.id).values(name="Renamed"),
        execution_options={"synchronize_session": False},
    )

    assert sheet_view(db, owner, character).character.name == "Test"
    assert refreshed_sheet_view(db, owner, character).character.name == "Renamed"


def test_someone_elses_sheet_is_not_found(client, theirs):
    assert client.get(f"/characters/{theirs.id}/sheet").status_code == 404


def test_the_sheet_through_the_app(client, character):
    url = f"/characters/{character.id}/sheet"
    assert client.get(url).status_code == 200

    response = client.post(f"{url}/hp", data={"action": "damage", "amount": "abc"})
    assert response.status_code == 400 and "Enter a whole number from 0 to 999." in response.text

    response = client.post(f"{url}/hp", data={"action": "damage", "amount": "3"})
    assert response.headers["HX-Retarget"] == "#sheet-page"
    assert "<strong>5</strong>" in response.text  # 8 max HP

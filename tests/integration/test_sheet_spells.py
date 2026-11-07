import pytest
from sqlalchemy import select

from app.sheet import service
from app.sheet.queries import (
    copy_search,
    prepared_editor_view,
    prepared_spell_ids,
    spell_slots,
)
from app.spells.models import Spell, SpellbookEntry
from app.spells.queries import spellbook


def _spell(db, slug: str) -> Spell:
    return db.scalar(select(Spell).where(Spell.slug == slug))


def _book(db, character) -> dict[str, SpellbookEntry]:
    return {e.spell.slug: e for e in spellbook(db, character.id)}


def _add(db, character, *slugs: str, via: str = "copied") -> list[str]:
    spells = [_spell(db, s) for s in slugs]
    db.add_all(
        SpellbookEntry(character_id=character.id, spell_id=spell.id, acquired_via=via)
        for spell in spells
    )
    db.flush()
    return [str(spell.id) for spell in spells]


# --- Prepared spells ----------------------------------------------------------------------


def test_preparing_spells_from_the_book(db, character):
    keys = _add(db, character, "test-spell-a", "test-spell-b")

    assert service.save_prepared(db, character, keys + keys[:1]) is None  # a repeat counts once

    assert prepared_spell_ids(db, character) == {int(k) for k in keys}
    assert sorted(prepared_editor_view(db, character).selected) == sorted(keys)
    # Only spells still in the book stay ticked, e.g. after one is removed.
    assert prepared_editor_view(db, character, [keys[0], "999999"]).selected == [keys[0]]


def test_an_invalid_preparation_changes_nothing(db, character):
    keys = _add(db, character, *(f"test-spell-{x}" for x in "abcde"))
    assert service.save_prepared(db, character, keys[:1]) is None

    error = service.save_prepared(db, character, [keys[0], "999999"])
    assert error == "You can only prepare spells in your spellbook."
    assert service.save_prepared(db, character, keys) == "You can prepare at most 4. You picked 5."

    assert prepared_spell_ids(db, character) == {int(keys[0])}


def test_a_non_caster_cant_prepare(db, warlock):
    assert service.save_prepared(db, warlock, []) == "This character doesn't prepare spells."


def test_removing_a_copied_spell_unprepares_it(db, character, prepare_from_book):
    spell = _spell(db, "test-spell-a")
    prepare_from_book(character, spell.id)
    key = str(spell.id)

    assert service.remove_copied_spell(db, character, key) is None

    db.expire_all()
    assert "test-spell-a" not in _book(db, character)
    assert prepared_spell_ids(db, character) == set()


def test_a_level_up_spell_isnt_removed_here(db, character):
    [key] = _add(db, character, "test-spell-a", via="level_up")

    error = service.remove_copied_spell(db, character, key)

    assert (
        error == "Only copied spells can be removed here. Change level-up spells on the Build page."
    )
    assert "test-spell-a" in _book(db, character)


# --- Slots and casting --------------------------------------------------------------------


def test_setting_slots(db, character):
    assert service.change_slots(db, character, 1, "1") is None
    assert spell_slots(db, character)[1].remaining == 1


@pytest.mark.parametrize(("level", "remaining"), [(1, "3"), (1, "²"), (1, "x"), (9, "1")])
def test_an_invalid_slot_count_changes_nothing(db, character, level, remaining):
    error = service.change_slots(db, character, level, remaining)

    assert error == "That isn't a valid number of slots."
    assert spell_slots(db, character)[1].remaining == 2


# --- Copying spells -----------------------------------------------------------------------


def test_copying_a_spell_with_its_note(db, character):
    spell = _spell(db, "test-spell-a")

    assert service.copy_spell(db, character, str(spell.id), "  From a scroll  ") is None

    entry = _book(db, character)["test-spell-a"]
    assert (entry.acquired_via, entry.source_note) == ("copied", "From a scroll")


def test_only_spells_of_level_1_or_higher_are_copied(db, character):
    for key in ["999999", "²", str(_spell(db, "test-cantrip-a").id)]:
        error = service.copy_spell(db, character, key, "")
        assert error == "Choose a spell of level 1 or higher to copy."

    assert _book(db, character) == {}


def test_a_spell_already_in_the_book_isnt_copied_again(db, character):
    [key] = _add(db, character, "test-spell-a")

    assert (
        service.copy_spell(db, character, key, "") == "Test Spell A is already in your spellbook."
    )
    assert [e.acquired_via for e in _book(db, character).values()] == ["copied"]
    reasons = {
        spell.slug: why for spell, why, _ in copy_search(db, character, "Test Spell").results
    }
    assert reasons["test-spell-a"] == "In your spellbook"


# --- Requests -----------------------------------------------------------------------------


def test_only_in_play_choices_are_set_on_the_sheet(client, character, wizard_choice):
    url = f"/characters/{character.id}/sheet/choices/{wizard_choice('skills').id}"
    assert client.post(url, data={"pick": "1"}).status_code == 404


def test_someone_elses_sheet_spells_are_not_found(client, theirs):
    sheet = f"/characters/{theirs.id}/sheet"
    assert client.get(f"{sheet}/prepared/edit").status_code == 404
    for path in (
        "prepared",
        "prepared/edit",
        "spellbook/remove",
        "slots/1",
        "cast",
        "cast-free",
        "spellbook/copy",
    ):
        assert client.post(f"{sheet}/{path}").status_code == 404


def test_only_copyable_spells_reach_the_confirm_step(client, db, character):
    url = f"/characters/{character.id}/sheet/spellbook/copy/confirm"
    for key in ["²", str(_spell(db, "test-cantrip-a").id)]:
        assert client.get(url, params={"spell": key}).status_code == 404


def test_spells_through_the_app(client, db, character):
    sheet = f"/characters/{character.id}/sheet"
    [key] = _add(db, character, "test-spell-a")
    assert "Test Spell A" in client.get(f"{sheet}/prepared/edit").text

    response = client.post(f"{sheet}/prepared", data={"picks": ["999999"]})
    assert response.status_code == 400 and "only prepare spells in your spellbook" in response.text

    response = client.post(f"{sheet}/prepared", data={"picks": [key]})
    assert response.headers["HX-Retarget"] == "#sheet-page"

    spell_b = _spell(db, "test-spell-b")
    assert "Test Spell B" in client.get(f"{sheet}/spellbook/copy/search", params={"q": "Test"}).text
    confirm = client.get(
        f"{sheet}/spellbook/copy/confirm", params={"spell": spell_b.id, "q": "Test"}
    )
    assert "2 hours and 50 GP" in confirm.text

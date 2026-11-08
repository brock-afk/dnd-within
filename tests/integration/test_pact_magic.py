from sqlalchemy import select

from app.classes.models import CharacterClass
from app.features.kinds import KINDS
from app.features.models import Choice, Feature
from app.leveling.service import level_down
from app.sheet.queries import castable_spells, spell_slots
from app.sheet.service import finish_short_rest, set_slots_remaining
from app.spells.models import Spell


def _class_id(db, slug: str) -> int:
    return db.scalar(select(CharacterClass.id).where(CharacterClass.slug == slug))


def _spell_id(db, slug: str) -> int:
    return db.scalar(select(Spell.id).where(Spell.slug == slug))


def _choice(db) -> Choice:
    return db.scalar(
        select(Choice)
        .join(Feature, Feature.id == Choice.feature_id)
        .where(Feature.class_id == _class_id(db, "test-pact"), Choice.slug == "spells")
    )


def _names(db, character) -> list[str]:
    return [o.name for o in KINDS["spell"].options(db, _choice(db), character)]


def test_pact_slots_follow_the_class_level(db, warlock, level_up):
    [slot] = spell_slots(db, warlock).values()
    assert (slot.level, slot.maximum, slot.kind) == (1, 1, "pact")

    level_up(warlock, 3)
    [slot] = spell_slots(db, warlock).values()
    assert (slot.level, slot.maximum) == (2, 2)


def test_short_rest_restores_pact_slots_only(db, warlock, character):
    set_slots_remaining(db, warlock, 1, 0)
    set_slots_remaining(db, character, 1, 0)
    db.flush()

    finish_short_rest(db, warlock)
    finish_short_rest(db, character)
    db.expire_all()

    assert spell_slots(db, warlock)[1].remaining == 1
    assert spell_slots(db, character)[1].remaining == 0


def test_spell_choice_offers_spells_up_to_the_slot_level(db, warlock, level_up):
    assert _names(db, warlock) == ["Pact Spell A", "Pact Spell B"]
    too_high = str(_spell_id(db, "pact-spell-c"))
    assert KINDS["spell"].save(db, _choice(db), warlock.id, [too_high]) is not None

    level_up(warlock, 3)
    assert _names(db, warlock) == ["Pact Spell A", "Pact Spell B", "Pact Spell C"]
    assert KINDS["spell"].save(db, _choice(db), warlock.id, [too_high]) is None


def test_picked_spells_are_cast_with_pact_slots(client, db, warlock):
    spell = _spell_id(db, "pact-spell-a")
    assert KINDS["spell"].save(db, _choice(db), warlock.id, [str(spell)]) is None
    db.commit()

    [row] = [r for r in castable_spells(db, warlock) if r.spell.id == spell]
    assert row.prepared and row.uses_slots

    sheet = f"/characters/{warlock.id}/sheet"
    response = client.post(f"{sheet}/cast", data={"spell": spell, "slot_level": "1"})
    assert response.status_code == 200
    db.expire_all()
    assert spell_slots(db, warlock)[1].remaining == 0

    assert client.post(f"{sheet}/short-rest/finish").status_code == 200
    db.expire_all()
    assert spell_slots(db, warlock)[1].remaining == 1


def test_spell_both_picked_and_prepared_from_a_book_is_listed_once(db, warlock, prepare_from_book):
    spell = _spell_id(db, "pact-spell-a")
    assert KINDS["spell"].save(db, _choice(db), warlock.id, [str(spell)]) is None
    prepare_from_book(warlock, spell)

    assert [r.spell.id for r in castable_spells(db, warlock)].count(spell) == 1


def test_no_spellbook_tools_without_a_spellbook(client, warlock):
    page = client.get(f"/characters/{warlock.id}/sheet").text
    assert "Copy a spell" not in page
    assert "/sheet/prepared/edit" not in page


def test_always_prepared_spell_cant_be_picked(client, db, warlock):
    url = f"/characters/{warlock.id}/choices/{_choice(db).id}"
    response = client.post(url, data={"picks": [_spell_id(db, "pact-spell-b")]})

    assert response.status_code == 400
    assert "Pact Spell B is always prepared (Patron Gift)." in response.text


def test_level_down_drops_spells_above_the_slot_level(db, warlock, level_up):
    level_up(warlock, 3)
    level_2 = str(_spell_id(db, "pact-spell-c"))
    assert KINDS["spell"].save(db, _choice(db), warlock.id, [level_2]) is None

    while warlock.level > 2:
        assert level_down(db, warlock, str(warlock.level)) is None
    db.expire_all()

    assert KINDS["spell"].picked(db, _choice(db), warlock.id) == []

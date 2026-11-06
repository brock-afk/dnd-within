"""Eldritch Invocation mechanics, with the fixture pack's Test Pact invocations: a count that
grows with level, prerequisites, a spell cast at will (Armor of Shadows), and a pact with its
own any-class picks (Pact of the Tome)."""

from sqlalchemy import delete, select

from app.features.kinds import KINDS
from app.features.models import CharacterChoicePick, Choice, ChoiceOption
from app.features.service import feature_groups, remove_inapplicable_picks
from app.leveling.service import level_down
from app.sheet.models import CharacterAcEffect
from app.sheet.service import ac_spells, castable_spells, spell_slots
from app.spells.models import Spell


def _choice(db, slug: str = "invocations") -> Choice:
    return db.scalar(select(Choice).where(Choice.slug == slug))


def _key(db, slug: str) -> str:
    choice = _choice(db)
    option = db.scalar(
        select(ChoiceOption).where(ChoiceOption.choice_id == choice.id, ChoiceOption.slug == slug)
    )
    return str(option.id)


def _picked(db, character) -> list[str]:
    return [o.name for o in KINDS["option"].picked(db, _choice(db), character.id)]


def _choice_view(db, character, slug: str = "invocations"):
    return next(
        cv
        for g in feature_groups(db, character)
        for fv in g.features
        for cv in fv.choices
        if cv.choice.slug == slug
    )


def _save(db, character, *slugs: str, choice: str = "invocations") -> str | None:
    keys = [_key(db, s) for s in slugs]
    return KINDS["option"].save(db, _choice(db, choice), character.id, keys)


def _lose_levels_to(db, character, level: int) -> None:
    while character.level > level:
        assert level_down(db, character, str(character.level)) is None
    db.expire_all()


def test_count_grows_with_level(client, db, warlock, level_up):
    assert _choice_view(db, warlock).count == 1
    url = f"/characters/{warlock.id}/choices/{_choice(db).id}"
    two = [_key(db, "shadow-armor"), _key(db, "keen-mind")]
    response = client.post(url, data={"picks": two})
    assert response.status_code == 400 and "Choose one." in response.text

    level_up(warlock, 2)
    assert _choice_view(db, warlock).count == 3
    level_up(warlock, 5)
    assert _choice_view(db, warlock).count == 5


def test_level_down_drops_unmet_then_trims_newest(db, warlock, level_up):
    level_up(warlock, 5)
    assert (
        _save(db, warlock, "shadow-armor", "deep-gift", "blade-pact", "thirsting", "keen-mind")
        is None
    )

    _lose_levels_to(db, warlock, 4)

    # Deep Gift needs level 5; then the newest pick goes to fit 3.
    assert _picked(db, warlock) == ["Blade Pact", "Shadow Armor", "Thirsting"]


def test_prerequisites(db, warlock, level_up):
    level_up(warlock, 4)
    options = {o.name: o for o in KINDS["option"].options(db, _choice(db), warlock)}
    assert options["Deep Gift"].warnings == ("Needs Test Pact 5",)
    assert options["Thirsting"].warnings == ("Needs Blade Pact",)
    unavailable = KINDS["option"].unavailable(db, _choice(db), warlock.id)
    assert unavailable[_key(db, "deep-gift")] == "From Test Pact 5"
    assert _key(db, "thirsting") not in unavailable  # pickable together with Blade Pact

    assert _save(db, warlock, "deep-gift", "keen-mind", "shadow-armor") == (
        "Deep Gift needs Test Pact 5."
    )
    assert _save(db, warlock, "thirsting", "keen-mind", "shadow-armor") == (
        "Thirsting needs Blade Pact."
    )
    assert _save(db, warlock, "blade-pact", "thirsting", "keen-mind") is None

    # Unpicking Blade Pact (here directly) leaves Thirsting without its prerequisite.
    db.execute(
        delete(CharacterChoicePick).where(
            CharacterChoicePick.option_id == int(_key(db, "blade-pact"))
        )
    )
    remove_inapplicable_picks(db, warlock)
    db.expire_all()
    assert _picked(db, warlock) == ["Keen Mind"]


def test_ac_spell_cast_at_will(client, db, warlock):
    assert _save(db, warlock, "shadow-armor") is None
    db.commit()  # the requests below share this session
    armor = db.scalar(select(Spell).where(Spell.slug == "test-armor"))

    [row] = [r for r in castable_spells(db, warlock) if r.spell.id == armor.id]
    assert row.at_will and not row.uses_slots
    [offered] = ac_spells(db, warlock)
    assert (offered.spell.id, offered.slots, offered.at_will_from) == (armor.id, [], "Shadow Armor")
    assert "At will · Shadow Armor" in client.get(f"/characters/{warlock.id}/sheet").text

    sheet = f"/characters/{warlock.id}/sheet"
    response = client.post(
        f"{sheet}/ac-effects/cast", data={"spell": armor.id, "slot_level": "at_will"}
    )
    assert response.status_code == 200
    db.expire_all()
    effect = db.scalar(
        select(CharacterAcEffect).where(CharacterAcEffect.character_id == warlock.id)
    )
    assert (effect.spell_id, effect.kind, effect.value) == (armor.id, "base", 13)
    assert spell_slots(db, warlock)[1].remaining == 1  # no slot spent


def test_tome_picks_spells_from_any_class(client, db, warlock):
    assert _save(db, warlock, "tome-pact") is None
    db.commit()
    tome_cantrips, tome_rituals = _choice(db, "tome-cantrips"), _choice(db, "tome-rituals")
    assert _choice_view(db, warlock, "tome-cantrips")  # shown once the pact is picked

    cantrip = db.scalar(select(Spell).where(Spell.slug == "test-cantrip-a"))  # a Wizard cantrip
    ritual = db.scalar(select(Spell).where(Spell.slug == "find-familiar"))  # a Wizard ritual
    names = [o.name for o in KINDS["spell"].options(db, tome_rituals, warlock)]
    assert names == ["Find Familiar"]  # level 1 rituals only
    for choice, spell in [(tome_cantrips, cantrip), (tome_rituals, ritual)]:
        url = f"/characters/{warlock.id}/choices/{choice.id}"
        assert client.post(url, data={"picks": [spell.id]}).status_code == 200
    db.expire_all()

    rows = [(r.spell.slug, r.prepared, r.in_ritual_section) for r in castable_spells(db, warlock)]
    assert ("test-cantrip-a", False, False) in rows
    assert ("find-familiar", True, False) in rows and ("find-familiar", True, True) in rows

    # Swapping the pact away removes the book's picks with it.
    url = f"/characters/{warlock.id}/choices/{_choice(db).id}"
    assert client.post(url, data={"picks": [_key(db, "keen-mind")]}).status_code == 200
    db.expire_all()
    slugs = {r.spell.slug for r in castable_spells(db, warlock)}
    assert not slugs & {"test-cantrip-a", "find-familiar"}

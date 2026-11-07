"""Features owned by a choice option (a Fiendish Legacy's spells): they apply while the option
is picked, unlocked by level like the feature offering the choice. Uses the fixture pack's
Legacy Folk species."""

import pytest
from sqlalchemy import delete, select

from app.classes.models import CharacterClass
from app.content import loader
from app.content.importer import import_pack
from app.features.kinds import source_name
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature
from app.features.queries import feature_groups
from app.leveling.models import CharacterLevel
from app.sheet import service as sheet_service
from app.sheet.queries import attributes, castable_spells, feature_uses
from app.species.models import Species


def _option(db, slug: str) -> ChoiceOption:
    return db.scalar(
        select(ChoiceOption)
        .join(Choice, Choice.id == ChoiceOption.choice_id)
        .where(Choice.slug == "legacy", ChoiceOption.slug == slug)
    )


def _pick(db, character, slug: str) -> None:
    option = _option(db, slug)
    db.execute(
        delete(CharacterChoicePick).where(
            CharacterChoicePick.character_id == character.id,
            CharacterChoicePick.choice_id == option.choice_id,
        )
    )
    db.add(
        CharacterChoicePick(
            character_id=character.id, choice_id=option.choice_id, option_id=option.id
        )
    )
    db.flush()


def _level_up_to(db, character, level: int) -> None:
    wizard = db.scalar(select(CharacterClass.id).where(CharacterClass.slug == "wizard"))
    for n in range(character.level + 1, level + 1):
        character.levels.append(
            CharacterLevel(character_level=n, class_id=wizard, hp_method="fixed")
        )
    db.flush()


def _option_features(db, character) -> list[str]:
    return [
        fv.feature.slug
        for group in feature_groups(db, character)
        for fv in group.features
        if fv.feature.option_id is not None
    ]


@pytest.fixture
def legacy_folk(db, character):
    """The level 1 test character, as Legacy Folk with no legacy picked yet."""
    character.species_id = db.scalar(select(Species.id).where(Species.slug == "legacy-folk"))
    db.flush()
    db.refresh(character)
    return character


def test_import_gives_options_their_features(db):
    ember = _option(db, "ember")
    features = db.scalars(
        select(Feature).where(Feature.option_id == ember.id).order_by(Feature.position)
    ).all()

    assert [f.slug for f in features] == ["ember-cantrip", "ember-spell"]
    assert source_name(db, features[0]) == "Legacy Folk"


def test_features_follow_the_pick_and_the_level(db, legacy_folk):
    assert _option_features(db, legacy_folk) == []

    _pick(db, legacy_folk, "ember")
    assert _option_features(db, legacy_folk) == ["ember-cantrip"]

    _level_up_to(db, legacy_folk, 3)
    assert _option_features(db, legacy_folk) == ["ember-cantrip", "ember-spell"]

    _pick(db, legacy_folk, "frost")
    assert _option_features(db, legacy_folk) == ["frost-cantrip", "frost-spell"]


def test_granted_spells_cast_free_once_per_long_rest(client, db, legacy_folk):
    _pick(db, legacy_folk, "ember")
    _level_up_to(db, legacy_folk, 3)

    rows = {row.spell.slug: row for row in castable_spells(db, legacy_folk)}
    assert "test-cantrip-a" in rows
    spell = rows["test-spell-a"]
    assert spell.free_cast and spell.granted_by.slug == "ember-spell"
    assert "fire" in attributes(db, legacy_folk).resistances

    def remaining() -> int:
        [uses] = [u for u in feature_uses(db, legacy_folk) if u.feature.slug == "ember-spell"]
        return uses.remaining

    sheet = f"/characters/{legacy_folk.id}/sheet"
    form = {"spell": spell.spell.id, "feature": spell.granted_by.id}
    assert client.post(f"{sheet}/cast-free", data=form).status_code == 200
    db.expire_all()
    assert remaining() == 0

    assert client.post(f"{sheet}/long-rest").status_code == 200
    db.expire_all()
    assert remaining() == 1


def _ember_caster(db, legacy_folk) -> tuple[str, str]:
    """Legacy Folk with the Ember legacy at level 3: the (spell, feature) keys of its free
    Test Spell A."""
    _pick(db, legacy_folk, "ember")
    _level_up_to(db, legacy_folk, 3)
    [row] = [r for r in castable_spells(db, legacy_folk) if r.spell.slug == "test-spell-a"]
    return str(row.spell.id), str(row.granted_by.id)


def test_a_used_free_cast_is_refused(db, legacy_folk):
    spell, feature = _ember_caster(db, legacy_folk)
    assert sheet_service.cast_free(db, legacy_folk, spell, feature) is None

    error = sheet_service.cast_free(db, legacy_folk, spell, feature)

    assert error.endswith("free cast is used. It comes back on a long rest.")


@pytest.mark.parametrize(
    ("field", "value"), [("spell", "²"), ("spell", "999999"), ("feature", "999999")]
)
def test_a_spell_that_isnt_cast_free_changes_nothing(db, legacy_folk, field, value):
    spell, feature = _ember_caster(db, legacy_folk)
    form = {"spell": spell, "feature": feature} | {field: value}

    assert sheet_service.cast_free(db, legacy_folk, **form) == "That spell can't be cast for free."
    [uses] = [u for u in feature_uses(db, legacy_folk) if u.feature.slug == "ember-spell"]
    assert uses.remaining == 1


def test_reimport_retires_what_the_pack_drops(db):
    def reimport(change=None):
        packs = loader.discover()
        by_slug = {p.slug: p for p in packs}
        pack = by_slug["test-core"]
        if change:
            change(next(s for s in pack.species if s.slug == "legacy-folk"))
        import_pack(db, pack, by_slug)
        db.expire_all()

    def drop_ember_spell_and_frost(species):
        choice = species.features[0].choices[0]
        ember = next(o for o in choice.options if o.slug == "ember")
        ember.features = [f for f in ember.features if f.slug != "ember-spell"]
        choice.options = [ember]

    ids_before = set(db.scalars(select(Feature.id).where(Feature.option_id.is_not(None))))
    reimport(drop_ember_spell_and_frost)

    def retired(slug: str) -> bool:
        return db.scalar(select(Feature.retired_at).where(Feature.slug == slug)) is not None

    assert not retired("ember-cantrip")
    assert retired("ember-spell")
    assert retired("frost-cantrip") and retired("frost-spell")
    assert _option(db, "frost").retired_at is not None

    reimport()
    assert not any(retired(s) for s in ["ember-spell", "frost-cantrip", "frost-spell"])
    assert set(db.scalars(select(Feature.id).where(Feature.option_id.is_not(None)))) == ids_before

import pytest
from sqlalchemy import select

from app.content.models import Source
from app.features.models import Feature
from app.inventory.models import CharacterItem, Item
from app.sheet.models import CharacterFeatureUse, CharacterHpEffect
from app.sheet.rests import long_rest
from app.sheet.service import hp_view, play_state


def test_long_rest_ends_max_hp_effects_and_restores_hp(db, character):
    db.add_all(
        [
            CharacterHpEffect(character_id=character.id, label="Wight drain", max_hp_delta=-3),
            CharacterHpEffect(character_id=character.id, label="Aid", max_hp_delta=5),
        ]
    )
    play_state(db, character).current_hp = 2
    db.flush()
    assert hp_view(db, character).maximum == 10

    long_rest(db, character)
    db.flush()

    hp = hp_view(db, character)
    assert hp.effects == []
    assert (hp.current, hp.maximum) == (8, 8)


def _wand(db, character, regain, expended, attuned=True) -> Feature:
    """A magic item with charges that regain `regain` dice at dawn, `expended` of them spent."""
    source = db.scalar(select(Source).where(Source.slug == "phb-2024"))
    wand = Item(
        source_id=source.id,
        slug="test-wand",
        name="Test Wand",
        category="magic",
        rarity="uncommon",
        summary="",
        requires_attunement=True,
    )
    db.add(wand)
    db.flush()
    charges = Feature(
        item_id=wand.id,
        slug="charges",
        name="Charges",
        summary="",
        uses={"max": 7, "recharge": "dawn", "regain": regain},
    )
    carried = CharacterItem(character_id=character.id, item_id=wand.id, attuned=attuned)
    db.add_all([charges, carried])
    db.flush()
    db.add(CharacterFeatureUse(character_id=character.id, feature_id=charges.id, expended=expended))
    db.flush()
    return charges


def _expended_after_long_rest(db, character, charges) -> int | None:
    long_rest(db, character)
    db.flush()
    row = db.get(CharacterFeatureUse, (character.id, charges.id))
    return row.expended if row else None


@pytest.mark.parametrize("attuned", [True, False])
def test_long_rest_rolls_regain_attuned_or_not(db, character, attuned):
    # An item regains its charges at dawn whether or not it's attuned. 1d1+1 is always 2.
    charges = _wand(db, character, "1d1+1", expended=6, attuned=attuned)
    assert _expended_after_long_rest(db, character, charges) == 4


def test_long_rest_never_spends_charges(db, character):
    # 1d1-2 rolls -1: regains nothing rather than spending one.
    charges = _wand(db, character, "1d1-2", expended=2)
    assert _expended_after_long_rest(db, character, charges) == 2

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


@pytest.mark.parametrize("attuned", [True, False])
def test_long_rest_rolls_regain_attuned_or_not(db, character, attuned):
    # A wand with 7 charges that regains 1d1+1 (always 2) at dawn, whether attuned or not.
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
        uses={"max": 7, "recharge": "dawn", "regain": "1d1+1"},
    )
    db.add_all(
        [charges, CharacterItem(character_id=character.id, item_id=wand.id, attuned=attuned)]
    )
    db.flush()
    db.add(CharacterFeatureUse(character_id=character.id, feature_id=charges.id, expended=6))
    db.flush()

    long_rest(db, character)
    db.flush()

    row = db.get(CharacterFeatureUse, (character.id, charges.id))
    assert row is not None and row.expended == 4

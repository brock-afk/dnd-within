"""A spell a feature already gives as always prepared can't be written into the spellbook or
prepared again: that would waste a pick."""

import pytest
from sqlalchemy import select

from app.content.models import Source
from app.features.kinds import KINDS
from app.features.models import Feature, FeatureSpell
from app.inventory.models import CharacterItem, Item
from app.spells.models import Spell

KNOWN = '<span class="choice-known">Always prepared (Familiar Gift)</span>'
REFUSED = "Find Familiar is always prepared (Familiar Gift)."


@pytest.fixture
def find_familiar(db, character) -> Spell:
    """Find Familiar, always prepared through a carried charm's Familiar Gift."""
    source = db.scalar(select(Source).where(Source.slug == "test-core"))
    spell = db.scalar(select(Spell).where(Spell.slug == "find-familiar"))
    charm = Item(
        source_id=source.id, slug="test-charm", name="Test Charm", category="magic", summary=""
    )
    db.add(charm)
    db.flush()
    gift = Feature(item_id=charm.id, slug="familiar-gift", name="Familiar Gift", summary="")
    db.add(gift)
    db.flush()
    db.add_all(
        [
            FeatureSpell(feature_id=gift.id, spell_id=spell.id),
            CharacterItem(character_id=character.id, item_id=charm.id),
        ]
    )
    db.flush()
    return spell


def test_level_up_spellbook_choice_blocks_it(db, client, character, find_familiar, wizard_choice):
    choice = wizard_choice("spellbook")
    url = f"/characters/{character.id}/choices/{choice.id}"
    assert KNOWN in client.get(url).text

    options = KINDS["spellbook"].options(db, choice, character)
    others = [o.key for o in options if o.name != "Find Familiar"]
    picks = [str(find_familiar.id), *others[: choice.count - 1]]
    response = client.post(url, data={"picks": picks})
    assert response.status_code == 400
    assert REFUSED in response.text


def test_copy_panel_blocks_it(client, character, find_familiar):
    search = client.get(f"/characters/{character.id}/sheet/spellbook/copy/search?q=Find Fam")
    assert KNOWN in search.text

    response = client.post(
        f"/characters/{character.id}/sheet/spellbook/copy", data={"spell": find_familiar.id}
    )
    assert response.status_code == 400
    assert REFUSED in response.text


@pytest.fixture
def prepared_from_book(character, find_familiar, prepare_from_book):
    """Find Familiar also in the spellbook and prepared from it, as picked before the block."""
    prepare_from_book(character, find_familiar.id)


def test_prepare_editor_blocks_it(client, character, find_familiar, prepared_from_book):
    assert KNOWN in client.get(f"/characters/{character.id}/sheet/prepared/edit").text

    response = client.post(
        f"/characters/{character.id}/sheet/prepared", data={"picks": [find_familiar.id]}
    )
    assert response.status_code == 400
    assert REFUSED in response.text


def test_it_doesnt_count_toward_the_prepare_limit(client, character, prepared_from_book):
    # A level 1 Wizard prepares 4.
    assert "0/4 prepared" in client.get(f"/characters/{character.id}/sheet").text

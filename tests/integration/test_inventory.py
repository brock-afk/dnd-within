from datetime import datetime

import pytest
from sqlalchemy import select

from app.content.models import Source
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature
from app.homebrew.form import ItemForm
from app.homebrew.queries import library_view
from app.homebrew.service import save_from_form
from app.inventory import service
from app.inventory.form import CoinChangeForm, CoinForm
from app.inventory.models import CharacterItem, Item
from app.inventory.queries import coin_values, healing_uses, inventory
from app.sheet.queries import armor_class, hp_view
from app.sheet.service import play_state
from app.spells.models import Spell


def _item(db, slug: str, source: str = "test-core", **fields) -> Item:
    source_id = db.scalar(select(Source.id).where(Source.slug == source))
    item = Item(
        source_id=source_id,
        slug=slug,
        name=fields.pop("name", slug.replace("-", " ").title()),
        category=fields.pop("category", "gear"),
        summary="",
        **fields,
    )
    db.add(item)
    db.flush()
    return item


def _carry(db, character, item: Item, quantity: int = 1, **fields) -> CharacterItem:
    row = CharacterItem(character_id=character.id, item_id=item.id, quantity=quantity, **fields)
    db.add(row)
    db.flush()
    return row


def _carried(db, character) -> dict[str, int]:
    db.expire_all()
    return {row.name: row.quantity for row in inventory(db, character)}


def _armor(db) -> Spell:
    return db.scalar(select(Spell).where(Spell.slug == "test-armor"))


# --- Adding from the catalog --------------------------------------------------------------


def test_adding_stacks_onto_the_carried_row(db, character):
    rope = _item(db, "rope")

    assert service.add_from_catalog(db, character, rope, "2", "") is None
    assert service.add_from_catalog(db, character, rope, " 3 ", "") is None

    assert _carried(db, character) == {"Rope": 5}


def test_a_pack_adds_its_contents(db, character):
    rope, torch = _item(db, "rope"), _item(db, "torch")
    contents = [{"item_id": rope.id, "quantity": 1}, {"item_id": torch.id, "quantity": 10}]
    pack = _item(db, "test-pack", category="pack", contents=contents)

    assert service.add_from_catalog(db, character, pack, "2", "") is None

    assert _carried(db, character) == {"Rope": 2, "Torch": 20}


def test_a_scroll_holds_a_spell_of_its_level(db, character):
    scroll = _item(db, "scroll-1", category="scroll", spell_level=1, consumable=True)
    cantrip = db.scalar(select(Spell.id).where(Spell.slug == "test-cantrip-a"))

    assert (
        service.add_from_catalog(db, character, scroll, "1", "")
        == "Choose the spell on the scroll."
    )
    error = service.add_from_catalog(db, character, scroll, "1", str(cantrip))
    assert error == "A Scroll 1 holds a spell of that level."
    assert _carried(db, character) == {}

    retired = db.scalar(select(Spell).where(Spell.slug == "test-spell-b"))
    retired.retired_at = datetime(2026, 1, 1)
    db.flush()
    error = service.add_from_catalog(db, character, scroll, "1", str(retired.id))
    assert error == "Choose the spell on the scroll."
    assert _carried(db, character) == {}

    assert service.add_from_catalog(db, character, scroll, "1", str(_armor(db).id)) is None
    [row] = inventory(db, character)
    assert row.spell.slug == "test-armor"


@pytest.mark.parametrize("quantity", ["0", "1000", "²", "x", ""])
def test_a_bad_quantity_adds_nothing(db, character, quantity):
    error = service.add_from_catalog(db, character, _item(db, "rope"), quantity, "")

    assert error == "Quantity is 1 to 999."
    assert _carried(db, character) == {}


# --- Carried items ------------------------------------------------------------------------


def test_quantity_never_drops_below_one(db, character):
    row = _carry(db, character, _item(db, "rope"))

    assert service.change_quantity(db, row, "1") is None
    assert service.change_quantity(db, row, "-1") is None
    assert service.change_quantity(db, row, "-1") is None
    assert service.change_quantity(db, row, "5") == "Use − or + to change the quantity."

    assert _carried(db, character) == {"Rope": 1}


def test_using_a_consumable_uses_one_up(db, character):
    potion = _carry(db, character, _item(db, "potion", consumable=True))
    rope = _carry(db, character, _item(db, "rope"))

    assert service.use_item(db, rope) == "Rope isn't used up."
    assert service.use_item(db, potion) is None

    assert _carried(db, character) == {"Rope": 1}


def test_notes_are_trimmed(db, character):
    row = _carry(db, character, _item(db, "rope"))

    service.set_notes(db, row, "  " + "x" * 300)
    assert row.notes == "x" * 255
    service.set_notes(db, row, "   ")
    assert row.notes is None


def test_removing_an_item(db, character):
    row = _carry(db, character, _item(db, "rope"), quantity=3)

    service.remove_item(db, character, row)

    assert _carried(db, character) == {}


# --- Healing and AC scrolls ---------------------------------------------------------------


def test_a_potion_heals_and_says_how_much(db, character):
    _carry(db, character, _item(db, "potion", consumable=True, healing="2"), quantity=2)
    play_state(db, character).current_hp = 7
    [use] = healing_uses(inventory(db, character))

    outcome = service.heal_with(db, character, use)

    assert outcome == (None, "Potion: healed 1 (2), 1 over your max.")
    assert hp_view(db, character).current == 8
    assert _carried(db, character) == {"Potion": 1}


def test_an_ac_scroll_starts_its_effect_once(db, character):
    scroll = _item(db, "scroll-1", category="scroll", spell_level=1, consumable=True)
    row = _carry(db, character, scroll, quantity=2, spell_id=_armor(db).id)

    assert service.cast_ac_scroll(db, character, row) is None
    assert [e.label for e in armor_class(db, character).effects] == ["Test Armor"]

    assert service.cast_ac_scroll(db, character, row) == "Test Armor is already on."
    assert _carried(db, character) == {"Spell Scroll: Test Armor": 1}


# --- Attunement ---------------------------------------------------------------------------


def _tool_pick(db, character, item: Item) -> CharacterChoicePick:
    """An attuned item's feature with a choice the character picked, like an item's tool."""
    feature = Feature(item_id=item.id, slug="gift", name="Gift", summary="")
    db.add(feature)
    db.flush()
    choice = Choice(feature_id=feature.id, slug="gift-pick", name="Gift", kind="option")
    db.add(choice)
    db.flush()
    option = ChoiceOption(choice_id=choice.id, slug="a", name="A", summary="")
    db.add(option)
    db.flush()
    pick = CharacterChoicePick(character_id=character.id, choice_id=choice.id, option_id=option.id)
    db.add(pick)
    db.flush()
    return pick


def test_attunement_is_limited_and_ending_it_drops_its_picks(db, character):
    rows = [
        _carry(db, character, _item(db, f"ring-{n}", requires_attunement=True)) for n in range(4)
    ]
    for row in rows[:3]:
        assert service.attune(db, character, row, "1") is None
    error = service.attune(db, character, rows[3], "1")
    assert error == "You can be attuned to at most 3 items. End one first."
    assert not rows[3].attuned

    pick = _tool_pick(db, character, rows[0].item)
    assert service.attune(db, character, rows[0], "") is None

    db.expire_all()
    assert db.get(CharacterChoicePick, pick.id) is None


def test_an_item_without_attunement_isnt_attuned(db, character):
    row = _carry(db, character, _item(db, "rope"))

    assert service.attune(db, character, row, "1") == "Rope doesn't need attunement."
    assert not row.attuned


# --- Coins --------------------------------------------------------------------------------


def test_gaining_and_spending_coins(db, character):
    service.set_coins(db, character, {"gp": 1, "sp": 0})

    assert service.change_coins(db, character, CoinChangeForm(amount="2", action="gain")) is None
    form = CoinChangeForm(amount=" 5 ", coin="sp", action="spend")
    assert service.change_coins(db, character, form) is None

    assert coin_values(db, character) == {"pp": 0, "gp": 2, "ep": 0, "sp": 5, "cp": 0}


@pytest.mark.parametrize(
    ("form", "error"),
    [
        ({"amount": "²", "action": "gain"}, "Enter how many coins, e.g. 15."),
        ({"amount": "0", "action": "gain"}, "Enter how many coins, e.g. 15."),
        ({"amount": "1000000", "action": "gain"}, "That's more than 1,000,000 gold."),
        (
            {"amount": "+0200", "action": "spend"},
            "You don't have 200 gold, even breaking larger coins.",
        ),
        ({"amount": "1", "coin": "zz", "action": "gain"}, "Choose a coin, then Add or Spend."),
        ({"amount": "1", "action": "steal"}, "Choose a coin, then Add or Spend."),
    ],
)
def test_a_bad_coin_change_changes_nothing(db, character, form, error):
    service.set_coins(db, character, {"pp": 1, "gp": 5})

    assert service.change_coins(db, character, CoinChangeForm(**form)) == error

    assert coin_values(db, character) == {"pp": 1, "gp": 5, "ep": 0, "sp": 0, "cp": 0}


def test_setting_every_coin(db, character):
    form = CoinForm(pp="", gp="1000000", ep="0", sp=" 3 ", cp="")
    assert service.save_coins(db, character, form) is None
    assert coin_values(db, character) == {"pp": 0, "gp": 1_000_000, "ep": 0, "sp": 3, "cp": 0}

    form = CoinForm(gp="5", sp="²")
    assert (
        service.save_coins(db, character, form) == "Silver is a whole number from 0 to 1,000,000."
    )
    assert coin_values(db, character)["gp"] == 1_000_000


# --- Requests -----------------------------------------------------------------------------


def test_someone_elses_inventory_is_not_found(client, db, character, theirs):
    their_row = _carry(db, theirs, _item(db, "rope"))
    db.commit()
    # Their row, on their sheet and on yours.
    for owner in (theirs, character):
        base = f"/characters/{owner.id}/sheet/inventory/{their_row.id}"
        assert client.get(f"{base}/remove").status_code == 404
        for path in ("quantity", "use", "heal", "cast-ac", "attune", "notes", "remove"):
            assert client.post(f"{base}/{path}").status_code == 404
    base = f"/characters/{theirs.id}/sheet/inventory"
    assert client.get(f"{base}/add").status_code == 404
    assert client.post(f"{base}/coins", data={"gp": "1"}).status_code == 404


def test_rows_of_the_wrong_kind_are_not_found(client, db, character):
    row = _carry(db, character, _item(db, "rope"))
    db.commit()
    base = f"/characters/{character.id}/sheet/inventory/{row.id}"

    assert client.post(f"{base}/heal").status_code == 404
    assert client.post(f"{base}/cast-ac").status_code == 404


def test_only_catalog_items_can_be_added(client, db, character, other_user):
    retired = _item(db, "old-rope", retired_at=datetime(2026, 1, 1))
    form = ItemForm(name="Their Ring", rarity="common", summary="Not yours.")
    assert save_from_form(db, other_user, form, None, None) == {}
    [(homebrew, _)] = library_view(db, other_user).items
    db.commit()
    base = f"/characters/{character.id}/sheet/inventory/add"

    for key in [str(retired.id), str(homebrew.id), "999999", "²", ""]:
        assert client.get(f"{base}/confirm", params={"item": key}).status_code == 404
        assert client.post(base, data={"item_id": key}).status_code == 404


def test_adding_through_the_app(client, db, character):
    rope = _item(db, "rope", name="Test Rope")
    db.commit()
    base = f"/characters/{character.id}/sheet/inventory"

    assert "Item name" in client.get(f"{base}/add").text
    assert "Test Rope" in client.get(f"{base}/add/search", params={"q": "Test R"}).text
    assert "Add to inventory" in client.get(f"{base}/add/confirm", params={"item": rope.id}).text

    response = client.post(f"{base}/add", data={"item_id": rope.id, "quantity": "0"})
    assert response.status_code == 400 and "Quantity is 1 to 999." in response.text

    response = client.post(f"{base}/add", data={"item_id": rope.id, "quantity": "2"})
    assert response.headers["HX-Retarget"] == "#sheet-page"
    assert _carried(db, character) == {"Test Rope": 2}

    [row] = inventory(db, character)
    assert "Remove Test Rope (all 2)?" in client.get(f"{base}/{row.id}/remove").text


def test_coins_through_the_app(client, character):
    base = f"/characters/{character.id}/sheet/inventory/coins"

    response = client.post(f"{base}/change", data={"amount": "x", "coin": "sp", "action": "gain"})
    assert response.status_code == 400
    assert "Enter how many coins, e.g. 15." in response.text
    assert 'value="x"' in response.text and '<option value="sp" selected' in response.text

    response = client.post(base, data={"gp": "²"})
    assert response.status_code == 400 and "Gold is a whole number" in response.text
    assert 'value="²"' in response.text

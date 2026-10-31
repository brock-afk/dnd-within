"""Where the Play sheet shows features and picked options, as their content says: Actions for
ones with an action or a `when`, a row of Attributes for passive ones with `sheet`, and nowhere
(the Build page only) for the rest."""

from sqlalchemy import select

from app.content.models import Source
from app.features.kinds import KINDS
from app.features.models import Choice, ChoiceOption, Feature
from app.inventory.models import CharacterItem, Item
from app.sheet.service import sheet_features


def _pick(db, character, *slugs: str) -> None:
    choice = db.scalar(select(Choice).where(Choice.slug == "invocations"))
    options = {
        o.slug: str(o.id)
        for o in db.scalars(select(ChoiceOption).where(ChoiceOption.choice_id == choice.id))
    }
    assert KINDS["option"].save(db, choice, character.id, [options[s] for s in slugs]) is None
    db.flush()


def _all_names(features) -> list[str]:
    names = [e.name for _, entries in features.actions for e in entries]
    return names + [e.name for entries in features.traits.values() for e in entries]


def test_actions_grouped_by_what_using_them_takes(db, warlock, level_up):
    level_up(warlock, 2)
    _pick(db, warlock, "blade-pact", "thirsting", "keen-mind")

    features = sheet_features(db, warlock)

    groups = [(label, [e.name for e in entries]) for label, entries in features.actions]
    assert groups == [
        ("Bonus Actions", ["Blade Pact"]),
        ("Triggered", ["Patron's Favor", "Thirsting"]),
    ]
    favor = features.actions[1][1][0]
    assert (favor.source, favor.when) == ("Test Pact", "When an enemy drops to 0 Hit Points")
    assert features.actions[0][1][0].source == "Invocations"
    assert features.actions_digest == "Blade Pact · Patron's Favor · Thirsting"


def test_passive_ones_go_to_their_attributes_row(db, warlock, level_up):
    level_up(warlock, 2)
    _pick(db, warlock, "keen-mind", "plain-gift", "dark-sight")

    features = sheet_features(db, warlock)

    traits = {row: [e.name for e in entries] for row, entries in features.traits.items()}
    assert traits == {
        "saves": ["Patron's Whisper"],
        "traits": ["Keen Mind"],
        "senses": ["Dark Sight"],
    }
    # Untagged ones and the features that only hold choices or give spells stay off the sheet.
    names = _all_names(features)
    for hidden in ["Plain Gift", "Pact Magic", "Invocations", "Patron Gift"]:
        assert hidden not in names


def test_resources_and_inventory_keep_theirs(db, warlock, stone_giant):
    # Giant Ancestry has uses: its picked boon (Stone's Endurance) is listed in Resources.
    assert not any("Stone" in n for n in _all_names(sheet_features(db, stone_giant)))

    source = db.scalar(select(Source).where(Source.slug == "test-core"))
    ring = Item(
        source_id=source.id, slug="test-ring", name="Test Ring", category="magic", summary=""
    )
    db.add(ring)
    db.flush()
    glow = Feature(item_id=ring.id, slug="glow", name="Glow", summary="It glows.", sheet="traits")
    db.add_all([glow, CharacterItem(character_id=warlock.id, item_id=ring.id)])
    db.flush()
    assert "Glow" not in _all_names(sheet_features(db, warlock))


def test_sheet_and_build_page(client, db, warlock):
    _pick(db, warlock, "dark-sight")
    db.commit()  # the requests below share this session

    sheet = client.get(f"/characters/{warlock.id}/sheet").text
    assert 'id="section-actions"' in sheet and "Triggered" in sheet  # Patron's Favor
    attributes = sheet[sheet.index('id="section-attributes"') :]
    senses = attributes[
        attributes.index("<dt>Senses</dt>") : attributes.index(
            "</dd>", attributes.index("<dt>Senses</dt>")
        )
    ]
    assert "Darkvision 60 ft" in senses and "Dark Sight" in senses
    assert "<dt>Saving throws</dt>" in attributes and "Advantage on saves against" in attributes

    build = client.get(f"/characters/{warlock.id}").text
    assert "See in magical darkness too." in build


def test_build_page_shows_every_picked_option(client, db, warlock, level_up):
    level_up(warlock, 2)
    _pick(db, warlock, "blade-pact", "thirsting", "keen-mind")
    db.commit()

    build = client.get(f"/characters/{warlock.id}").text
    for summary in ["A pact weapon.", "Needs the Blade Pact.", "Text only."]:
        assert summary in build

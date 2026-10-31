"""The Play sheet's Features section, grouped by what using each row takes (features with uses,
in-play choices, and ones whose content gives an action or a `when`), and passive features in
their Attributes row. Untagged ones are for the Build page only."""

from sqlalchemy import select

from app.content.models import Source
from app.features.kinds import KINDS
from app.features.models import Choice, ChoiceOption, Feature, FeatureSpell
from app.features.service import feature_groups, play_choices
from app.inventory.models import CharacterItem, Item
from app.sheet.rests import feature_uses
from app.sheet.service import sheet_features
from app.spells.models import Spell


def _features(db, character):
    groups = feature_groups(db, character)
    choices = play_choices(db, character, groups)
    return sheet_features(db, character, groups, feature_uses(db, character, groups), choices)


def _name(row) -> str:
    if row.spender:
        return row.spender.name
    if row.uses:
        return row.uses.feature.name
    return row.choice.picked.name if row.choice else row.entry.name


def _groups(features) -> dict[str, list[str]]:
    return {label: [_name(r) for r in rows] for label, rows in features.groups}


def _all_names(features) -> list[str]:
    names = [_name(r) for _, rows in features.groups for r in rows]
    return names + [e.name for entries in features.traits.values() for e in entries]


def _pick(db, character, *slugs: str) -> None:
    choice = db.scalar(select(Choice).where(Choice.slug == "invocations"))
    options = {
        o.slug: str(o.id)
        for o in db.scalars(select(ChoiceOption).where(ChoiceOption.choice_id == choice.id))
    }
    assert KINDS["option"].save(db, choice, character.id, [options[s] for s in slugs]) is None
    db.flush()


def test_rows_grouped_by_what_using_them_takes(db, warlock, level_up):
    level_up(warlock, 2)
    _pick(db, warlock, "blade-pact", "thirsting", "keen-mind")

    features = _features(db, warlock)

    # Giant Ancestry (the fixture Goliath's) has uses but no boon picked: nothing says when.
    assert _groups(features) == {
        "Bonus Actions": ["Blade Pact"],
        "Triggered": ["Patron's Favor", "Thirsting"],
        "Other": ["Giant Ancestry"],
    }
    favor = features.groups[1][1][0].entry
    assert (favor.source, favor.when) == ("Test Pact", "When an enemy drops to 0 Hit Points")
    assert features.groups[0][1][0].entry.source == "Invocations"
    assert features.digest == "Blade Pact · Patron's Favor · Thirsting · Giant Ancestry 2/2"


def test_tracked_features_grouped_by_option_or_spell(db, warlock, stone_giant, level_up):
    # Stone's Endurance is a reaction, so Giant Ancestry's uses are under Reactions.
    assert _groups(_features(db, stone_giant))["Reactions"] == ["Giant Ancestry"]

    level_up(warlock, 5)
    _pick(db, warlock, "deep-gift", "keen-mind")
    groups = _groups(_features(db, warlock))
    assert groups["Actions"] == ["Deep Gift"]  # its free spell takes an action
    assert "Large Form" in groups["Other"]  # uses, and nothing says what using it takes


def test_passive_ones_go_to_their_attributes_row(db, warlock, level_up):
    level_up(warlock, 2)
    _pick(db, warlock, "keen-mind", "plain-gift", "dark-sight")

    features = _features(db, warlock)

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
    # `sheet: none` (deliberately Build page only) is stored as no placement.
    plain = db.scalar(select(ChoiceOption).where(ChoiceOption.slug == "plain-gift"))
    assert plain.sheet is None


def test_options_of_tracked_features_and_item_abilities_stay_in_their_row(db, warlock, stone_giant):
    # Giant Ancestry lists its picked boon (Stone's Endurance) in its own row.
    assert not any("Stone" in n for n in _all_names(_features(db, stone_giant)))

    source = db.scalar(select(Source).where(Source.slug == "test-core"))
    ring = Item(
        source_id=source.id, slug="test-ring", name="Test Ring", category="magic", summary=""
    )
    db.add(ring)
    db.flush()
    glow = Feature(item_id=ring.id, slug="glow", name="Glow", summary="It glows.", sheet="traits")
    db.add_all([glow, CharacterItem(character_id=warlock.id, item_id=ring.id)])
    db.flush()
    assert "Glow" not in _all_names(_features(db, warlock))


def test_sheet_and_build_page(client, db, warlock):
    _pick(db, warlock, "dark-sight")
    db.commit()  # the requests below share this session

    sheet = client.get(f"/characters/{warlock.id}/sheet").text
    assert 'id="section-features"' in sheet and "Triggered" in sheet  # Patron's Favor
    assert 'id="section-resources"' not in sheet and 'id="section-actions"' not in sheet
    attributes = sheet[sheet.index('id="section-attributes"') :]
    start = attributes.index("<dt>Senses</dt>")
    senses = attributes[start : attributes.index("</dd>", start)]
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


def test_pips_and_free_casts_still_work(client, db, warlock, level_up):
    level_up(warlock, 5)
    _pick(db, warlock, "deep-gift", "keen-mind")
    db.commit()
    gift = db.scalar(
        select(Feature).where(Feature.slug == "deep-gift", Feature.option_id.is_not(None))
    )
    sheet = f"/characters/{warlock.id}/sheet"

    form = {"spell": gift.spells[0].spell_id, "feature": gift.id}
    response = client.post(f"{sheet}/cast-free", data=form)
    assert response.status_code == 200 and "0 of 1" in response.text
    response = client.post(f"{sheet}/uses/{gift.id}", data={"remaining": "1"})
    assert response.status_code == 200 and "1 of 1" in response.text


def test_rows_say_what_they_do(client, db, warlock, stone_giant, level_up):
    level_up(warlock, 5)
    _pick(db, warlock, "deep-gift", "keen-mind")
    db.commit()

    # A tracked feature without picked options shows its own summary; the full rules text is
    # for the Build page.
    sheet = client.get(f"/characters/{warlock.id}/sheet").text
    assert "Cast Pact Spell A once per Long Rest without a spell slot." in sheet
    assert "Full text" not in sheet and "The full rules text of Deep Gift." not in sheet
    # A tracked feature's own timing is a tag too (and puts it under Triggered).
    assert '<span class="spell-tag">When you finish a Short Rest</span>' in sheet

    # A picked boon's timing is a tag, not a bold heading.
    sheet = client.get(f"/characters/{stone_giant.id}/sheet").text
    assert '<span class="spell-tag">When you take damage</span>' in sheet
    assert "<strong>When you take damage" not in sheet


def test_item_abilities_get_their_own_rows(client, db, warlock):
    """Like the Tome of Bal'vir: a pool of charges, and abilities that spend them."""
    source = db.scalar(select(Source).where(Source.slug == "test-core"))
    tome = Item(
        source_id=source.id, slug="test-tome", name="Test Tome", category="magic", summary=""
    )
    db.add(tome)
    db.flush()
    charges = Feature(
        item_id=tome.id,
        slug="charges",
        name="Test Tome charges",  # as the homebrew editor names them
        summary="3 charges.",
        uses={"max": 3, "recharge": "dawn"},
    )
    db.add_all([charges, CharacterItem(character_id=warlock.id, item_id=tome.id)])
    db.flush()
    # Like the Tome's Disguise Self: a spell its charges cast, which takes an action. The pool
    # still goes under Other, since abilities spend it too.
    spell = db.scalar(select(Spell.id).where(Spell.slug == "test-spell-a"))
    db.add_all(
        [
            FeatureSpell(
                feature_id=charges.id, spell_id=spell, free_cast=True, always_prepared=False
            ),
            Feature(
                item_id=tome.id,
                slug="quick",
                name="Quick Trick",
                summary="Fast.",
                action="bonus_action",
                spends_feature_id=charges.id,
                spends_amount=1,
            ),
            Feature(
                item_id=tome.id,
                slug="parry",
                name="Parry",
                summary="Block.",
                action="reaction",
                spends_feature_id=charges.id,
                spends_amount=1,
            ),
        ]
    )
    db.commit()

    features = _features(db, warlock)

    rows = {label: rows for label, rows in features.groups}
    [quick] = [r for r in rows["Bonus Actions"] if _name(r) == "Quick Trick"]
    [parry] = [r for r in rows["Reactions"] if _name(r) == "Parry"]
    [pool] = [r for r in rows["Other"] if _name(r) == "Test Tome charges"]
    assert quick.source == parry.source == pool.source == "Test Tome"
    assert pool.name == "Charges"  # its source isn't repeated

    sheet = f"/characters/{warlock.id}/sheet"
    response = client.post(f"{sheet}/features/{quick.spender.id}/use")
    assert response.status_code == 200 and "2 of 3" in response.text

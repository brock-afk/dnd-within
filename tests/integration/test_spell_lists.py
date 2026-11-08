from datetime import datetime

import pytest
from sqlalchemy import select

from app.classes.models import CharacterClass
from app.content.models import Source
from app.features.kinds import KINDS
from app.homebrew.form import ItemForm, build_item_def
from app.homebrew.queries import editor_view
from app.homebrew.service import homebrew_source
from app.inventory.models import Item
from app.inventory.queries import scroll_spells
from app.inventory.service import add_from_catalog
from app.sheet.queries import copy_search, copyable
from app.spells.models import Spell


def _spell(db, source: Source, slug: str) -> Spell:
    wizard = db.scalar(select(CharacterClass).where(CharacterClass.slug == "wizard"))
    spell = Spell(
        source_id=source.id,
        slug=slug,
        name=f"Listed {slug.title()}",
        level=1,
        school="abjuration",
        casting_unit="action",
        summary="",
    )
    spell.classes.append(wizard)
    db.add(spell)
    db.flush()
    return spell


def _scroll(db) -> Item:
    source = db.scalar(select(Source).where(Source.slug == "test-core"))
    scroll = Item(
        source_id=source.id,
        slug="scroll-1",
        name="Scroll",
        category="scroll",
        spell_level=1,
        summary="",
    )
    db.add(scroll)
    db.flush()
    return scroll


@pytest.fixture
def spells(db, owner, other_user) -> dict[str, Spell]:
    retired = db.scalar(select(Spell).where(Spell.slug == "test-spell-b"))
    retired.retired_at = datetime(2026, 1, 1)
    return {
        "mine": _spell(db, homebrew_source(db, owner), "mine"),
        "theirs": _spell(db, homebrew_source(db, other_user), "theirs"),
        "retired": retired,
    }


@pytest.mark.parametrize(
    ("which", "offered"), [("mine", True), ("theirs", False), ("retired", False)]
)
def test_lists_and_lookups_agree(db, owner, character, wizard_choice, spells, which, offered):
    spell = spells[which]
    key = str(spell.id)

    choice = wizard_choice("spellbook")
    kind = KINDS[choice.kind]
    assert (key in {o.key for o in kind.options(db, choice, character)}) is offered
    assert (kind.save(db, choice, character.id, [key]) is None) is offered

    found = {s.id for s, _, _ in copy_search(db, character, spell.name).results}
    assert (spell.id in found) is offered
    assert (copyable(db, key, owner.id) is not None) is offered

    scroll = _scroll(db)
    assert (spell in scroll_spells(db, scroll, owner.id)) is offered
    assert (add_from_catalog(db, character, scroll, "1", key) is None) is offered

    assert (spell in editor_view(db, owner, ItemForm(), None).spells) is offered
    form = ItemForm(
        name="Wand",
        rarity="common",
        summary="A wand.",
        charges="3",
        spell_id=[key],
        spell_charges=["1"],
    )
    _, errors = build_item_def(db, form, owner.id)
    assert ("spells" not in errors) is offered

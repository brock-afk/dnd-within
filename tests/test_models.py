import pytest
from sqlalchemy import JSON
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.core.db import Base


def test_nullable_json_columns_store_sql_null():
    plain = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, JSON) and column.nullable and not column.type.none_as_null
    ]
    assert plain == []


@pytest.mark.parametrize(
    ("table", "check"),
    [
        (
            "character_ability_bonuses",
            "ck_character_ability_bonuses_ability_values"
            " CHECK (ability IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA'))",
        ),
        (
            "features",
            "ck_features_action_values CHECK (action IN ('action', 'bonus_action', 'reaction'))",
        ),
        (
            "choice_options",
            "ck_choice_options_action_values"
            " CHECK (action IN ('action', 'bonus_action', 'reaction'))",
        ),
        (
            "items",
            "ck_items_category_values"
            " CHECK (category IN ('gear', 'consumable', 'pack', 'scroll', 'tool', 'magic'))",
        ),
        (
            "items",
            "ck_items_rarity_values CHECK (rarity IN"
            " ('common', 'uncommon', 'rare', 'very_rare', 'legendary', 'artifact'))",
        ),
        (
            "spells",
            "ck_spells_casting_unit_values"
            " CHECK (casting_unit IN ('action', 'bonus_action', 'reaction', 'minute', 'hour'))",
        ),
        (
            "spells",
            "ck_spells_school_values CHECK (school IN ('abjuration', 'conjuration', 'divination',"
            " 'enchantment', 'evocation', 'illusion', 'necromancy', 'transmutation'))",
        ),
        (
            "character_spell_slots",
            "ck_character_spell_slots_kind_values CHECK (kind IN ('spellcasting', 'pact'))",
        ),
        (
            "spellbook_entries",
            "ck_spellbook_entries_acquired_via_values"
            " CHECK (acquired_via IN ('level_up', 'feature', 'copied'))",
        ),
    ],
)
def test_enum_check_constraints_match_their_migrations(table, check):
    ddl = str(CreateTable(Base.metadata.tables[table]).compile(dialect=mysql.dialect()))
    assert f"CONSTRAINT {check}" in ddl

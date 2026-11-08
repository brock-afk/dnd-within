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
    ],
)
def test_enum_check_constraints_match_their_migrations(table, check):
    ddl = str(CreateTable(Base.metadata.tables[table]).compile(dialect=mysql.dialect()))
    assert f"CONSTRAINT {check}" in ddl

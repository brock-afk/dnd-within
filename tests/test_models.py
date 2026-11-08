import pytest
from sqlalchemy import JSON

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
    ("table", "name", "sql"),
    [
        (
            "character_ability_bonuses",
            "ability_values",
            "ability IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA')",
        ),
        ("features", "action_values", "action IN ('action', 'bonus_action', 'reaction')"),
        ("choice_options", "action_values", "action IN ('action', 'bonus_action', 'reaction')"),
    ],
)
def test_enum_check_constraints_match_their_migrations(table, name, sql):
    [constraint] = [
        c for c in Base.metadata.tables[table].constraints if str(c.name).endswith(name)
    ]
    assert str(constraint.sqltext) == sql

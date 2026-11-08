from sqlalchemy import JSON

from app.abilities.models import CharacterAbilityBonus
from app.core.db import Base


def test_nullable_json_columns_store_sql_null():
    plain = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, JSON) and column.nullable and not column.type.none_as_null
    ]
    assert plain == []


def test_the_ability_check_constraint_is_unchanged():
    [constraint] = [
        c
        for c in CharacterAbilityBonus.__table__.constraints
        if str(c.name).endswith("ability_values")
    ]
    assert str(constraint.sqltext) == "ability IN ('STR', 'DEX', 'CON', 'INT', 'WIS', 'CHA')"

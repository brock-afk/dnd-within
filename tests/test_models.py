from sqlalchemy import JSON

from app.core.db import Base


def test_nullable_json_columns_store_sql_null():
    # Plain JSON stores None as JSON null, which `IS NULL` filters don't match: use NullableJSON.
    plain = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, JSON) and column.nullable and not column.type.none_as_null
    ]
    assert plain == []

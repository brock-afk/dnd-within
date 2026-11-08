from contextlib import contextmanager

from sqlalchemy import event

from app.core.db import engine

MAX_QUERIES = 46
MAX_DAMAGE_PROMPT_QUERIES = 71


@contextmanager
def count_queries():
    queries = []

    def count(*args):
        statement = args[2]
        if "SAVEPOINT" not in statement:
            queries.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", count)


def test_play_sheet_query_count(client, character):
    with count_queries() as queries:
        response = client.get(f"/characters/{character.id}/sheet")
    assert response.status_code == 200
    assert len(queries) <= MAX_QUERIES, "\n".join(queries)


def test_damage_prompt_query_count(client, stone_giant):
    with count_queries() as queries:
        response = client.post(
            f"/characters/{stone_giant.id}/sheet/hp", data={"action": "damage", "amount": "5"}
        )
    assert "Taking 5 damage" in response.text and "Stone&#39;s Endurance" in response.text
    assert len(queries) <= MAX_DAMAGE_PROMPT_QUERIES, "\n".join(queries)

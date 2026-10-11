from sqlalchemy import event

from app.core.db import engine

# The Play sheet re-renders after every action, so it should look up the character's features
# once, not once per section (46 queries here; it was 140 when each section looked them up).
MAX_QUERIES = 46


def test_play_sheet_query_count(client, character):
    queries = []

    def count(*args):
        queries.append(args[2])  # the statement

    event.listen(engine, "before_cursor_execute", count)
    try:
        assert client.get(f"/characters/{character.id}/sheet").status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert len(queries) <= MAX_QUERIES

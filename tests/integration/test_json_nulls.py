from sqlalchemy import select, text

from app.features.models import ChoiceOption


def test_play_sheet_with_a_picked_option_without_grants(client, stone_giant):
    assert client.get(f"/characters/{stone_giant.id}/sheet").status_code == 200


def test_new_rows_store_sql_null(db):
    stone = db.scalar(select(ChoiceOption).where(ChoiceOption.slug == "stone"))
    option = ChoiceOption(
        choice_id=stone.choice_id, slug="test", name="Test", summary="", grants=None
    )  # set explicitly, as the importer does
    db.add(option)
    db.flush()
    sql_null = text("SELECT grants IS NULL FROM choice_options WHERE id = :id")
    assert db.scalar(sql_null, {"id": option.id}) == 1

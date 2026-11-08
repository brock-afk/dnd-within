from sqlalchemy import select, text

from app.features.models import ChoiceOption
from app.features.rules import Action


def test_an_action_is_stored_as_its_value_and_read_back_as_the_enum(db):
    stone = db.scalar(select(ChoiceOption).where(ChoiceOption.slug == "stone"))
    option = ChoiceOption(
        choice_id=stone.choice_id, slug="test", name="Test", summary="", action="bonus_action"
    )
    db.add(option)
    db.flush()
    stored = text("SELECT action FROM choice_options WHERE id = :id")
    assert db.scalar(stored, {"id": option.id}) == "bonus_action"
    db.expire(option)
    assert option.action is Action.BONUS_ACTION

import pytest

from app.features.models import Feature
from app.sheet import service
from app.sheet.queries import feature_uses, spender


def _uses(db, character, slug: str):
    return next(u for u in feature_uses(db, character) if u.feature.slug == slug)


@pytest.fixture
def blast(db, character, charged_item) -> Feature:
    """An ability of a 3-charge item that takes 2 of them."""
    charges = charged_item(character, {"max": 3, "recharge": "dawn"})
    blast = Feature(
        item_id=charges.item_id,
        slug="blast",
        name="Blast",
        summary="",
        spends_feature_id=charges.id,
        spends_amount=2,
    )
    db.add(blast)
    db.flush()
    return blast


def test_setting_uses(db, character):
    uses = _uses(db, character, "giant-ancestry")

    assert service.change_uses(db, character, uses, "1") is None

    assert _uses(db, character, "giant-ancestry").remaining == 1


@pytest.mark.parametrize("remaining", ["x", "²", "3"])
def test_an_invalid_use_count_changes_nothing(db, character, remaining):
    uses = _uses(db, character, "giant-ancestry")

    error = service.change_uses(db, character, uses, remaining)

    assert error == "That isn't a valid number of uses."
    assert _uses(db, character, "giant-ancestry").remaining == 2


def test_an_ability_spends_its_pool(db, character, blast):
    assert service.use_spender(db, character, spender(db, character, blast.id)) is None
    assert spender(db, character, blast.id).uses.remaining == 1

    error = service.use_spender(db, character, spender(db, character, blast.id))

    assert error == "Blast takes 2; 1 left."
    assert spender(db, character, blast.id).uses.remaining == 1


def test_uses_are_changed_only_where_they_belong(client, db, character):
    sheet = f"/characters/{character.id}/sheet"
    ancestry = _uses(db, character, "giant-ancestry").feature.id
    recovery = _uses(db, character, "arcane-recovery").feature.id

    # Arcane Recovery is spent in the rest panel; Giant Ancestry recovers no slots and isn't
    # an ability that spends another's uses.
    assert client.post(f"{sheet}/uses/{recovery}", data={"remaining": "0"}).status_code == 404
    assert client.post(f"{sheet}/short-rest/recover/{ancestry}").status_code == 404
    assert client.post(f"{sheet}/features/{ancestry}/use").status_code == 404
    assert client.post(f"{sheet}/uses/999999", data={"remaining": "0"}).status_code == 404

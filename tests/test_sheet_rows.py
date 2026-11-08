from types import SimpleNamespace

import pytest

from app.sheet.queries import FeatureRow


def _row(name: str, source: str) -> FeatureRow:
    return FeatureRow(uses=SimpleNamespace(feature=SimpleNamespace(name=name)), source=source)


@pytest.mark.parametrize(
    ("name", "source", "shown"),
    [
        ("Tome of Bal'vir charges", "Tome of Bal'vir", "Charges"),
        ("Tome Fire Charges", "Tome", "Fire Charges"),
        ("Bardic Inspiration", "Bard", "Bardic Inspiration"),
        ("Monk's Focus", "Monk", "Monk's Focus"),
        ("Giant Ancestry", "Goliath", "Giant Ancestry"),
    ],
)
def test_row_name_drops_only_a_repeated_source(name, source, shown):
    assert _row(name, source).name == shown

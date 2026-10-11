import pytest

from app.abilities import rules
from app.abilities.rules import ABILITIES

COLUMNS = [a.column for a in ABILITIES]


def scores(*values):
    return dict(zip(COLUMNS, values, strict=True))


@pytest.mark.parametrize(
    ("score", "mod"), [(1, -5), (8, -1), (9, -1), (10, 0), (11, 0), (15, 2), (20, 5)]
)
def test_modifier(score, mod):
    assert rules.modifier(score) == mod


def test_parse_scores_blanks_and_junk_become_none():
    raw = {"strength": " 15 ", "dexterity": "", "constitution": "abc", "intelligence": "-1"}
    parsed = rules.parse_scores(raw)
    assert parsed["strength"] == 15
    assert parsed["dexterity"] is None
    assert parsed["constitution"] is None
    assert parsed["intelligence"] == -1
    assert parsed["charisma"] is None


def test_parse_rolls_pads_to_six():
    assert rules.parse_rolls(["12", "x"]) == [12, None, None, None, None, None]


def test_point_buy_full_budget_is_valid():
    s = scores(15, 15, 15, 8, 8, 8)  # 9 * 3 = 27
    assert rules.point_buy_spent(s) == 27
    assert rules.validate("point_buy", s) == {}


def test_point_buy_over_budget():
    errors = rules.validate("point_buy", scores(15, 15, 15, 9, 8, 8))
    assert "_form" in errors


def test_point_buy_out_of_range_score():
    errors = rules.validate("point_buy", scores(16, 8, 8, 8, 8, 8))
    assert "strength" in errors


def test_point_buy_step_respects_budget_and_range():
    s = scores(15, 15, 15, 8, 8, 8)
    rules.point_buy_step(s, "wisdom", +1)
    assert s["wisdom"] == 8  # no points left
    rules.point_buy_step(s, "strength", +1)
    assert s["strength"] == 15  # 16 isn't buyable
    rules.point_buy_step(s, "strength", -1)
    assert s["strength"] == 14


def test_standard_array_valid_and_reused_value():
    assert rules.validate("standard_array", scores(15, 14, 13, 12, 10, 8)) == {}
    assert "_form" in rules.validate("standard_array", scores(15, 15, 13, 12, 10, 8))


def test_unassigned_counts_duplicates():
    s = scores(15, 14, None, None, None, None)
    assert rules.unassigned([15, 15, 14, 10], s) == [15, 10]


def test_manual_rolls_must_be_complete_and_in_range():
    s = scores(10, 10, 10, 10, 10, 10)
    assert "rolls" in rules.validate("manual", s, [10, 10, 10, 10, 10, None])
    assert "rolls" in rules.validate("manual", s, [10, 10, 10, 10, 10, 19])
    assert rules.validate("manual", s, [10] * 6) == {}


def test_unknown_method():
    assert "_form" in rules.validate("nope", scores(*[10] * 6))

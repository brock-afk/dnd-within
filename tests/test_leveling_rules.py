import pytest

from app.leveling import rules


@pytest.mark.parametrize(("die", "fixed"), [(6, 4), (8, 5), (10, 6), (12, 7)])
def test_fixed_hp(die, fixed):
    assert rules.fixed_hp(die) == fixed


def test_die_result_by_method():
    assert rules.die_result("max", 10, None) == 10
    assert rules.die_result("fixed", 10, None) == 6
    assert rules.die_result("roll", 10, 3) == 3


def test_level_hp_is_at_least_one():
    assert rules.level_hp(1, -2) == 1
    assert rules.level_hp(6, 2) == 8

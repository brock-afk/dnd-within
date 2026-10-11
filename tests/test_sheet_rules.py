import random

import pytest

from app.sheet import rules
from app.sheet.models import CharacterPlayState


def state(current_hp=None, temp_hp=0, source=None):
    return CharacterPlayState(current_hp=current_hp, temp_hp=temp_hp, temp_hp_source=source)


@pytest.mark.parametrize(
    ("stored", "max_hp", "expected"),
    [(None, 20, 20), (12, 20, 12), (25, 20, 20), (-3, 20, 0)],
)
def test_current_hp(stored, max_hp, expected):
    assert rules.current_hp(state(stored), max_hp) == expected


def test_current_hp_without_state_is_full():
    assert rules.current_hp(None, 20) == 20


# The table in the app/sheet/rules.py docstring, row by row.
def test_increase_that_heals_adds_to_current():
    s = state(12)
    rules.apply_max_change(s, 20, 25, heal_increase=True)
    assert s.current_hp == 17


def test_increase_that_heals_keeps_full_at_full():
    s = state(None)
    rules.apply_max_change(s, 20, 25, heal_increase=True)
    assert s.current_hp is None


def test_decrease_caps_current():
    s = state(18)
    rules.apply_max_change(s, 20, 15, heal_increase=False)
    assert s.current_hp is None  # capped at 15, which is full


def test_decrease_below_current_max_leaves_damage():
    s = state(10)
    rules.apply_max_change(s, 20, 15, heal_increase=False)
    assert s.current_hp == 10


def test_drain_ending_does_not_heal():
    s = state(None)  # full at the drained max of 15
    rules.apply_max_change(s, 15, 20, heal_increase=False)
    assert s.current_hp == 15


def test_no_change_is_a_no_op():
    s = state(7)
    rules.apply_max_change(s, 20, 20, heal_increase=True)
    assert s.current_hp == 7


def test_temp_hp_absorbs_damage_first():
    s = state(None, temp_hp=5, source="False Life")
    rules.take_damage(s, 3, 20)
    assert (s.temp_hp, s.temp_hp_source, s.current_hp) == (2, "False Life", None)


def test_damage_past_temp_hp_clears_source_and_hits_current():
    s = state(None, temp_hp=5, source="False Life")
    rules.take_damage(s, 8, 20)
    assert (s.temp_hp, s.temp_hp_source, s.current_hp) == (0, None, 17)


def test_damage_stops_at_zero():
    s = state(4)
    rules.take_damage(s, 50, 20)
    assert s.current_hp == 0


def test_heal_caps_at_max_and_ignores_temp_hp():
    s = state(15, temp_hp=3)
    rules.heal(s, 10, 20)
    assert (s.current_hp, s.temp_hp) == (None, 3)


def test_temp_hp_replaces_and_drops_source_at_zero():
    s = state(temp_hp=5, source="False Life")
    rules.set_temp_hp(s, 8, "Heroism")
    assert (s.temp_hp, s.temp_hp_source) == (8, "Heroism")
    rules.set_temp_hp(s, 0, "Heroism")
    assert (s.temp_hp, s.temp_hp_source) == (0, None)


@pytest.mark.parametrize(
    ("level", "pb"), [(1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (13, 5), (17, 6), (20, 6)]
)
def test_proficiency_bonus(level, pb):
    assert rules.proficiency_bonus(level) == pb


@pytest.mark.parametrize(
    ("proficient", "expertise", "expected"),
    [(False, False, 3), (False, True, 3), (True, False, 6), (True, True, 9)],
)
def test_skill_bonus(proficient, expertise, expected):
    assert rules.skill_bonus(3, 3, proficient, expertise) == expected


def test_hit_die_healing_is_at_least_one():
    assert rules.hit_die_healing(1, -3) == 1
    assert rules.hit_die_healing(6, 2) == 8


def test_roll_plain_number():
    assert rules.roll_detail("5") == (5, "5")


def test_roll_dice_with_modifier_stays_in_range():
    rng = random.Random(0)
    for _ in range(200):
        total, shown = rules.roll_detail("2d4+2", rng)
        assert 4 <= total <= 10
        assert shown.startswith("2d4+2: ")

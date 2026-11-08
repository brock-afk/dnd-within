from app.sheet.slots import slot_kind, slot_maximums

PACT = [(1, 1), (2, 1), (2, 2), (2, 2), (2, 3), (2, 3), (2, 4), (2, 4), (2, 5), (2, 5)]
PACT += [(3, 5)] * 6 + [(4, 5)] * 4


def test_pact_magic_has_one_slot_level_per_class_level():
    for class_level, (count, level) in enumerate(PACT, start=1):
        assert slot_maximums("pact", class_level) == {level: count}, class_level


def test_full_caster_table_is_unchanged():
    assert slot_maximums("full", 1) == {1: 2}
    assert slot_maximums("full", 5) == {1: 4, 2: 3, 3: 2}


def test_pact_slots_are_their_own_pool():
    assert slot_kind("pact") == "pact"
    assert slot_kind("full") == "spellcasting"

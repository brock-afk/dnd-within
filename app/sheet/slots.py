"""Spell slot progressions from the 2024 Player's Handbook.

Content says which progression a class uses (`spellcasting.slots`); the tables live here
because they're standard across books, and multiclassing will combine them.
"""

# Slots per spell level (1-9) at each class level (1-20), for full casters like the Wizard.
FULL_CASTER = [
    [2],
    [3],
    [4, 2],
    [4, 3],
    [4, 3, 2],
    [4, 3, 3],
    [4, 3, 3, 1],
    [4, 3, 3, 2],
    [4, 3, 3, 3, 1],
    [4, 3, 3, 3, 2],
    [4, 3, 3, 3, 2, 1],
    [4, 3, 3, 3, 2, 1],
    [4, 3, 3, 3, 2, 1, 1],
    [4, 3, 3, 3, 2, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 2, 1, 1],
]

# Pact Magic (the Warlock): (slot level, number of slots) at each class level. Every slot is
# the same level.
PACT_MAGIC = [
    (1, 1),
    (1, 2),
    (2, 2),
    (2, 2),
    (3, 2),
    (3, 2),
    (4, 2),
    (4, 2),
    (5, 2),
    (5, 2),
    *[(5, 3)] * 6,
    *[(5, 4)] * 4,
]


def slot_maximums(progression: str, class_level: int) -> dict[int, int]:
    """{spell level: number of slots} at this class level."""
    if progression == "pact":
        level, count = PACT_MAGIC[class_level - 1]
        return {level: count}
    counts = FULL_CASTER[class_level - 1]
    return {level: count for level, count in enumerate(counts, start=1)}


def slot_kind(progression: str) -> str:
    """Which pool a progression's slots are tracked in. Pact Magic slots are separate from
    Spellcasting slots: they come back on a short rest, and a multiclass character has both."""
    return "pact" if progression == "pact" else "spellcasting"

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

PROGRESSIONS = {"full": FULL_CASTER}


def slot_maximums(progression: str, class_level: int) -> dict[int, int]:
    """{spell level: number of slots} at this class level."""
    counts = PROGRESSIONS[progression][class_level - 1]
    return {level: count for level, count in enumerate(counts, start=1)}

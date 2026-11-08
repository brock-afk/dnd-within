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
    if progression == "pact":
        level, count = PACT_MAGIC[class_level - 1]
        return {level: count}
    counts = FULL_CASTER[class_level - 1]
    return {level: count for level, count in enumerate(counts, start=1)}


def slot_kind(progression: str) -> str:
    return "pact" if progression == "pact" else "spellcasting"

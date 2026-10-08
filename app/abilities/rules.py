"""Ability score rules from the 2024 Player's Handbook."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ability:
    column: str  # column on Character holding the base score
    abbr: str  # "STR", also used in skills.ability and character_ability_bonuses.ability
    name: str


ABILITIES = [
    Ability("strength", "STR", "Strength"),
    Ability("dexterity", "DEX", "Dexterity"),
    Ability("constitution", "CON", "Constitution"),
    Ability("intelligence", "INT", "Intelligence"),
    Ability("wisdom", "WIS", "Wisdom"),
    Ability("charisma", "CHA", "Charisma"),
]

METHODS = {
    "standard_array": "Standard array",
    "point_buy": "Point buy",
    "manual": "Manual entry",
}

STANDARD_ARRAY = [15, 14, 13, 12, 10, 8]
POINT_BUY_COSTS = {8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9}
POINT_BUY_BUDGET = 27
MANUAL_RANGE = (3, 18)
MAX_SCORE = 20  # bonuses can't raise a score above this


def modifier(score: int) -> int:
    return (score - 10) // 2


def _to_int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value.lstrip("-").isdigit() else None


def parse_scores(raw: dict[str, str]) -> dict[str, int | None]:
    """Form strings to ints, keyed by column. Blank or non-numeric becomes None."""
    return {a.column: _to_int(raw.get(a.column)) for a in ABILITIES}


def parse_rolls(raw: list[str]) -> list[int | None]:
    """The six rolled numbers for manual entry, padded to six."""
    rolls = [_to_int(r) for r in raw[:6]]
    return rolls + [None] * (6 - len(rolls))


def point_buy_cost(score: int | None) -> int:
    return POINT_BUY_COSTS.get(score, 0)


def point_buy_spent(scores: dict[str, int | None]) -> int:
    """Points used so far, counting scores outside 8–15 as unpriced (they get their own error)."""
    return sum(point_buy_cost(s) for s in scores.values())


def point_buy_step(scores: dict[str, int | None], column: str, delta: int) -> None:
    """Move one score up or down by one, but only within 8–15 and the point budget."""
    current = scores.get(column) or 8
    new = current + delta
    if new not in POINT_BUY_COSTS:
        return
    if point_buy_spent(scores) - point_buy_cost(current) + point_buy_cost(new) > POINT_BUY_BUDGET:
        return
    scores[column] = new


def unassigned(pool: list[int], scores: dict[str, int | None]) -> list[int]:
    """Pool values not yet given to an ability (a multiset difference, so duplicates count)."""
    left = list(pool)
    for score in scores.values():
        if score in left:
            left.remove(score)
    return left


def validate(
    method: str, scores: dict[str, int | None], rolls: list[int | None] | None = None
) -> dict[str, str]:
    """Errors keyed by column, "rolls" for the manual pool, and "_form" for the set as a whole."""
    if method not in METHODS:
        return {"_form": "Choose how to set your scores."}

    errors = {}
    if method == "point_buy":
        for a in ABILITIES:
            if scores[a.column] not in POINT_BUY_COSTS:
                errors[a.column] = "Point buy scores are 8–15."
        spent = point_buy_spent(scores)
        if spent > POINT_BUY_BUDGET:
            errors["_form"] = f"That costs {spent} points; you have {POINT_BUY_BUDGET}."
        return errors

    # Standard array and manual both assign a pool of six values, each used once.
    if method == "standard_array":
        pool = STANDARD_ARRAY
    else:
        rolls = rolls or [None] * 6
        low, high = MANUAL_RANGE
        if any(r is None for r in rolls):
            errors["rolls"] = "Enter all six rolls."
        elif any(not low <= r <= high for r in rolls):
            errors["rolls"] = f"Rolls are {low}–{high}."
        pool = [r for r in rolls if r is not None]

    for a in ABILITIES:
        if scores[a.column] is None:
            errors[a.column] = "Choose a score."
    if not errors and sorted(scores.values()) != sorted(pool):
        errors["_form"] = (
            "Use each of 15, 14, 13, 12, 10 and 8 exactly once."
            if method == "standard_array"
            else "Use each roll exactly once."
        )
    return errors

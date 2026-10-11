"""Hit point rules from the 2024 Player's Handbook, and rolling dice.

Current HP is stored (NULL means "at full"); max HP is calculated. Whenever max HP changes,
`apply_max_change` adjusts current HP according to why it changed:

| event                                              | max HP | current HP                 |
| level up, Con increase, a positive effect starts   | +X     | +X                         |
| an effect ends, a level is removed, a drain starts | -X     | capped at the new max      |
| a negative effect (drain) ends                     | +X     | unchanged: it doesn't heal |
"""

import random
import re

from app.sheet.models import CharacterPlayState


def current_hp(state: CharacterPlayState | None, max_hp: int) -> int:
    if state is None or state.current_hp is None:
        return max_hp
    return max(0, min(state.current_hp, max_hp))


def _store(state: CharacterPlayState, value: int, max_hp: int) -> None:
    """Store current HP, using NULL for "at full" so later max increases keep you at full."""
    value = max(0, min(value, max_hp))
    state.current_hp = None if value >= max_hp else value


def apply_max_change(
    state: CharacterPlayState, old_max: int, new_max: int, heal_increase: bool
) -> None:
    """Adjust current HP after max HP changed from old_max to new_max.

    heal_increase: True when the increase also restores hit points (level up, Con increase,
    an effect like Aid starting); False when it doesn't (a drain wearing off).
    """
    if new_max == old_max:
        return
    current = current_hp(state, old_max)
    if new_max > old_max:
        if heal_increase:
            _store(state, current + (new_max - old_max), new_max)
        else:
            # Even "at full" stays at the old value: the new hit points weren't healed.
            _store(state, current, new_max)
    else:
        _store(state, min(current, new_max), new_max)


def take_damage(state: CharacterPlayState, amount: int, max_hp: int) -> None:
    """Temporary hit points absorb damage first; current HP stops at 0."""
    absorbed = min(state.temp_hp, amount)
    state.temp_hp -= absorbed
    if state.temp_hp == 0:
        state.temp_hp_source = None
    _store(state, current_hp(state, max_hp) - (amount - absorbed), max_hp)


def heal(state: CharacterPlayState, amount: int, max_hp: int) -> None:
    """Healing never goes above max HP and doesn't touch temporary hit points."""
    _store(state, current_hp(state, max_hp) + amount, max_hp)


def set_temp_hp(state: CharacterPlayState, amount: int, source: str | None) -> None:
    """Temporary hit points don't stack: the player keeps one amount, replacing the pool."""
    state.temp_hp = amount
    state.temp_hp_source = (source or None) if amount > 0 else None


def proficiency_bonus(character_level: int) -> int:
    """+2 at levels 1-4, +3 at 5-8, ... +6 at 17-20."""
    return 2 + (character_level - 1) // 4


def skill_bonus(ability_mod: int, pb: int, proficient: bool, expertise: bool) -> int:
    """Ability modifier, plus the proficiency bonus if proficient, or twice it with Expertise.
    Expertise only counts in a skill you're proficient in."""
    if not proficient:
        return ability_mod
    return ability_mod + pb * (2 if expertise else 1)


def hit_die_healing(roll: int, con_mod: int) -> int:
    """HP regained from one spent hit die: the roll plus Constitution modifier, at least 1."""
    return max(roll + con_mod, 1)


def roll(dice: str, rng: random.Random | None = None) -> int:
    """Roll "1d3" or "2d4+2"."""
    return roll_detail(dice, rng)[0]


def roll_detail(dice: str, rng: random.Random | None = None) -> tuple[int, str]:
    """Roll and say how: (9, "2d4+2: 3 + 4, +2"). A plain number ("5") is just itself.

    Numbers have at most three digits, like content validation allows. Anything bigger raises
    ValueError instead of rolling billions of dice."""
    rng = rng or random.Random()
    text = dice.replace(" ", "")
    if re.fullmatch(r"\d{1,3}", text):
        return int(text), text
    match = re.fullmatch(r"(\d{1,3})d(\d{1,3})([+-]\d{1,3})?", text)
    if match is None:
        raise ValueError(f"{dice!r} isn't dice notation within 999d999+999")
    count, sides, flat = int(match[1]), int(match[2]), int(match[3] or 0)
    rolls = [rng.randint(1, sides) for _ in range(count)]
    shown = " + ".join(str(r) for r in rolls) + (f", {flat:+d}" if flat else "")
    return sum(rolls) + flat, f"{text}: {shown}"

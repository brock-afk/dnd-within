"""Hit point rules from the 2024 Player's Handbook.

Current HP is stored (NULL means "at full"); max HP is calculated. Whenever max HP changes,
`apply_max_change` adjusts current HP according to why it changed:

| event                                              | max HP | current HP                 |
| level up, Con increase, a positive effect starts   | +X     | +X                         |
| an effect ends, a level is removed, a drain starts | -X     | capped at the new max      |
| a negative effect (drain) ends                     | +X     | unchanged: it doesn't heal |
"""

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


def hit_die_healing(roll: int, con_mod: int) -> int:
    """HP regained from one spent hit die: the roll plus Constitution modifier, at least 1."""
    return max(roll + con_mod, 1)

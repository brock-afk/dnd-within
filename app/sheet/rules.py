import random
import re

from app.sheet.models import CharacterPlayState


def current_hp(state: CharacterPlayState | None, max_hp: int) -> int:
    if state is None or state.current_hp is None:
        return max_hp
    return max(0, min(state.current_hp, max_hp))


def _store(state: CharacterPlayState, value: int, max_hp: int) -> None:
    value = max(0, min(value, max_hp))
    state.current_hp = None if value >= max_hp else value


def apply_max_change(
    state: CharacterPlayState, old_max: int, new_max: int, heal_increase: bool
) -> None:
    if new_max == old_max:
        return
    current = current_hp(state, old_max)
    if new_max > old_max:
        if heal_increase:
            _store(state, current + (new_max - old_max), new_max)
        else:
            _store(state, current, new_max)
    else:
        _store(state, min(current, new_max), new_max)


def take_damage(state: CharacterPlayState, amount: int, max_hp: int) -> None:
    absorbed = min(state.temp_hp, amount)
    state.temp_hp -= absorbed
    if state.temp_hp == 0:
        state.temp_hp_source = None
    _store(state, current_hp(state, max_hp) - (amount - absorbed), max_hp)


def heal(state: CharacterPlayState, amount: int, max_hp: int) -> None:
    _store(state, current_hp(state, max_hp) + amount, max_hp)


def set_temp_hp(state: CharacterPlayState, amount: int, source: str | None) -> None:
    state.temp_hp = amount
    state.temp_hp_source = (source or None) if amount > 0 else None


def proficiency_bonus(character_level: int) -> int:
    return 2 + (character_level - 1) // 4


def uses_maximum(maximum: int | str, character_level: int) -> int:
    return proficiency_bonus(character_level) if maximum == "proficiency_bonus" else maximum


def skill_bonus(ability_mod: int, pb: int, proficient: bool, expertise: bool) -> int:
    if not proficient:
        return ability_mod
    return ability_mod + pb * (2 if expertise else 1)


def hit_die_healing(roll: int, con_mod: int) -> int:
    return max(roll + con_mod, 1)


def roll(dice: str, rng: random.Random | None = None) -> int:
    return roll_detail(dice, rng)[0]


def roll_detail(dice: str, rng: random.Random | None = None) -> tuple[int, str]:
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

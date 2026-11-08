MAX_LEVEL = 20


def fixed_hp(hit_die: int) -> int:
    return hit_die // 2 + 1


def die_result(hp_method: str, hit_die: int, hp_roll: int | None) -> int:
    if hp_method == "max":
        return hit_die
    if hp_method == "fixed":
        return fixed_hp(hit_die)
    return hp_roll


def level_hp(die: int, con_mod: int) -> int:
    return max(die + con_mod, 1)

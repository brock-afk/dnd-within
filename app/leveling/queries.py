from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.abilities.queries import constitution_modifier
from app.characters.models import Character
from app.classes.models import CharacterClass
from app.leveling.rules import MAX_LEVEL, die_result, fixed_hp, level_hp


@dataclass(frozen=True)
class LevelHp:
    character_level: int
    class_name: str
    hp_method: str
    die: int
    con_mod: int

    @property
    def hp(self) -> int:
        return level_hp(self.die, self.con_mod)


@dataclass(frozen=True)
class HitPoints:
    levels: list[LevelHp]

    @property
    def maximum(self) -> int:
        return sum(level.hp for level in self.levels)

    @property
    def breakdown(self) -> str:
        return " · ".join(
            f"L{lv.character_level} {lv.class_name}: {lv.die} ({lv.hp_method}) "
            f"{'+' if lv.con_mod >= 0 else '−'}{abs(lv.con_mod)} CON = {lv.hp}"
            for lv in self.levels
        )


def hit_points(db: Session, character: Character) -> HitPoints | None:
    con_mod = constitution_modifier(db, character)
    if con_mod is None:
        return None
    return HitPoints(
        [
            LevelHp(
                lv.character_level,
                lv.character_class.name,
                lv.hp_method,
                die_result(lv.hp_method, lv.character_class.hit_die, lv.hp_roll),
                con_mod,
            )
            for lv in character.levels
        ]
    )


@dataclass(frozen=True)
class LevelUpView:
    character: Character
    class_name: str
    next_level: int
    at_max: bool
    hit_die: int
    con_mod: int | None
    fixed: int
    fixed_gain: int | None
    roll: str


def starting_class(character: Character) -> CharacterClass:
    return character.classes[0].character_class


def level_up_view(db: Session, character: Character, roll: str = "") -> LevelUpView:
    starting = starting_class(character)
    con_mod = constitution_modifier(db, character)
    fixed = fixed_hp(starting.hit_die)
    return LevelUpView(
        character=character,
        class_name=starting.name,
        next_level=character.level + 1,
        at_max=character.level >= MAX_LEVEL,
        hit_die=starting.hit_die,
        con_mod=con_mod,
        fixed=fixed,
        fixed_gain=level_hp(fixed, con_mod) if con_mod is not None else None,
        roll=roll,
    )

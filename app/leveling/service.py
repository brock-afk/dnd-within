from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.abilities.rules import modifier
from app.abilities.service import ability_views
from app.characters.models import Character
from app.leveling.rules import die_result, level_hp


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
        """e.g. "L1 Wizard: 6 (max) +2 CON = 8 · L2 Wizard: 4 (fixed) +2 CON = 6"."""
        return " · ".join(
            f"L{lv.character_level} {lv.class_name}: {lv.die} ({lv.hp_method}) "
            f"{'+' if lv.con_mod >= 0 else '−'}{abs(lv.con_mod)} CON = {lv.hp}"
            for lv in self.levels
        )


def constitution_modifier(db: Session, character: Character) -> int | None:
    """Uses the final score (base + bonuses), or None if scores aren't set yet."""
    abilities = ability_views(db, character)
    if abilities is None:
        return None
    con = next(a for a in abilities if a.abbr == "CON")
    return modifier(con.total)


def hit_points(db: Session, character: Character) -> HitPoints | None:
    """Max HP, or None until ability scores (and so Constitution) are set."""
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

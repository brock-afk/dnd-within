from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from app.core.forms import parse_amount

_AC_KINDS = {
    "base": (10, 30, "a base AC from 10 to 30 (e.g. Mage Armor, 13)"),
    "minimum": (10, 30, "a minimum AC from 10 to 30 (e.g. Barkskin, 17)"),
    "bonus": (-20, 20, "a non-zero bonus (e.g. Shield of Faith, +2)"),
}


class AcEffectForm(BaseModel):
    """By hand: Mage Armor base 13 (+ DEX), Shield of Faith bonus +2, Barkskin minimum 17."""

    model_config = ConfigDict(str_strip_whitespace=True)

    label: str = ""
    kind: str = ""
    value: str = ""

    @property
    def effect_kind(self) -> str:
        return self.kind if self.kind in _AC_KINDS else "bonus"

    def amount(self) -> int | None:
        low, high, _ = _AC_KINDS[self.effect_kind]
        return parse_amount(self.value, low, high)

    @property
    def hint(self) -> str:
        return _AC_KINDS[self.effect_kind][2]


class RecoveryForm(BaseModel):
    """How many slots of each level to recover; blank means none."""

    model_config = ConfigDict(str_strip_whitespace=True)

    level_1: str = ""
    level_2: str = ""
    level_3: str = ""
    level_4: str = ""
    level_5: str = ""
    level_6: str = ""
    level_7: str = ""
    level_8: str = ""
    level_9: str = ""

    def counts(self, levels: Iterable[int]) -> dict[int, int] | None:
        counts = {}
        for level in levels:
            count = parse_amount(getattr(self, f"level_{level}") or "0", 0, 99)
            if count is None:
                return None
            if count:
                counts[level] = count
        return counts

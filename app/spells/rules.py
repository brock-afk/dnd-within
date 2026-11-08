from enum import StrEnum

from app.core.enums import LabeledEnum
from app.features.rules import Action


class CastingUnit(StrEnum):
    ACTION = "action"
    BONUS_ACTION = "bonus_action"
    REACTION = "reaction"
    MINUTE = "minute"
    HOUR = "hour"

    @property
    def action(self) -> Action | None:
        return Action(self) if self in Action else None


class School(LabeledEnum):
    ABJURATION = "abjuration"
    CONJURATION = "conjuration"
    DIVINATION = "divination"
    ENCHANTMENT = "enchantment"
    EVOCATION = "evocation"
    ILLUSION = "illusion"
    NECROMANCY = "necromancy"
    TRANSMUTATION = "transmutation"


class DurationKind(StrEnum):
    INSTANTANEOUS = "instantaneous"
    TIMED = "timed"
    UNTIL_DISPELLED = "until_dispelled"
    SPECIAL = "special"


class DurationUnit(StrEnum):
    ROUND = "round"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"


class RangeKind(LabeledEnum):
    SELF = "self"
    TOUCH = "touch"
    DISTANCE = "distance"
    SIGHT = "sight"
    UNLIMITED = "unlimited"
    SPECIAL = "special"


class AreaShape(StrEnum):
    CONE = "cone"
    CUBE = "cube"
    CYLINDER = "cylinder"
    EMANATION = "emanation"
    LINE = "line"
    SPHERE = "sphere"
    SQUARE = "square"


class SaveOutcome(StrEnum):
    HALF = "half"
    NONE = "none"
    SPECIAL = "special"


class AttackKind(StrEnum):
    MELEE = "melee"
    RANGED = "ranged"


class AcquiredVia(StrEnum):
    LEVEL_UP = "level_up"
    FEATURE = "feature"
    COPIED = "copied"


class SlotKind(StrEnum):
    SPELLCASTING = "spellcasting"
    PACT = "pact"


class SlotProgression(StrEnum):
    FULL = "full"
    PACT = "pact"

    @property
    def slot_kind(self) -> SlotKind:
        return SlotKind.PACT if self == SlotProgression.PACT else SlotKind.SPELLCASTING


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


def slot_maximums(progression: SlotProgression, class_level: int) -> dict[int, int]:
    if progression == SlotProgression.PACT:
        level, count = PACT_MAGIC[class_level - 1]
        return {level: count}
    counts = FULL_CASTER[class_level - 1]
    return {level: count for level, count in enumerate(counts, start=1)}

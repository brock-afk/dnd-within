"""The shape of every file in a content pack. Packs are validated against these before
anything is imported, so mistakes are reported with their file instead of breaking pages.

Feature, choice and option definitions are shared with app/features/schema.py.
"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.features.schema import FeatureDef

Ability = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]
DamageType = Literal[
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic", "piercing",
    "poison", "psychic", "radiant", "slashing", "thunder",
]
School = Literal[
    "abjuration", "conjuration", "divination", "enchantment", "evocation", "illusion",
    "necromancy", "transmutation",
]

# "8d6", "1d4+1", "2d4 + 4", or a flat number like "5".
DICE = re.compile(r"^\s*(\d+d\d+(\s*[+-]\s*\d+)?|\d+)\s*$")


class Strict(BaseModel):
    """Unknown keys are errors, so a typo like `concentraton` isn't silently ignored."""

    model_config = ConfigDict(extra="forbid")


def _check_dice(value: str) -> str:
    if not DICE.match(value):
        raise ValueError(f"{value!r} isn't dice notation like 3d8 or 1d4+1")
    return value.replace(" ", "")


class PackMeta(Strict):
    slug: str
    name: str
    kind: Literal["official", "third_party", "homebrew"]
    version: int | str
    requires: list[str] = []


class SkillDef(Strict):
    slug: str
    name: str
    ability: Ability


class SpeciesDef(Strict):
    slug: str
    name: str
    summary: str
    features: list[FeatureDef] = []


class Spellcasting(Strict):
    """How a class casts spells. Spell slots will be added here too."""

    ability: Ability
    # Spells you can prepare at each class level, 1 through 20.
    prepared: list[int] = Field(min_length=20, max_length=20)
    # Which ritual spells you can cast as rituals: only prepared ones (the general rule), or any
    # in your spellbook without preparing them (the Wizard's Ritual Adept).
    ritual_casting: Literal["prepared", "spellbook"] = "prepared"
    # Spell slot progression; the tables themselves live in app/sheet/slots.py.
    slots: Literal["full"] = "full"


class ClassDef(Strict):
    slug: str
    name: str
    summary: str
    hit_die: Literal[6, 8, 10, 12]
    spellcasting: Spellcasting | None = None
    features: list[FeatureDef] = []


class SubclassDef(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    slug: str
    name: str
    class_: str = Field(alias="class")  # class slug, e.g. "wizard" or "phb-2024/wizard"
    summary: str
    features: list[FeatureDef] = []


# --- Spells -------------------------------------------------------------------------------


class CastingTime(Strict):
    unit: Literal["action", "bonus_action", "reaction", "minute", "hour"]
    amount: int = Field(default=1, ge=1)
    trigger: str | None = None  # required for reactions: "when you're hit by an attack roll"

    @model_validator(mode="after")
    def check(self):
        if (self.unit == "reaction") != (self.trigger is not None):
            raise ValueError("reactions need a trigger, and only reactions have one")
        return self


class Range(Strict):
    kind: Literal["self", "touch", "distance", "sight", "unlimited", "special"]
    feet: int | None = None
    miles: int | None = None

    @model_validator(mode="after")
    def check(self):
        has_distance = self.feet is not None or self.miles is not None
        if (self.kind == "distance") != has_distance:
            raise ValueError("a distance range needs feet or miles, and only it has them")
        return self


class Area(Strict):
    shape: Literal["cone", "cube", "cylinder", "emanation", "line", "sphere", "square"]
    feet: int
    width_feet: int | None = None  # lines
    height_feet: int | None = None  # cylinders


class Material(Strict):
    text: str
    cost_gp: int | None = None  # only for components with a listed price
    consumed: bool = False


class Components(Strict):
    verbal: bool = False
    somatic: bool = False
    material: Material | None = None


class Duration(Strict):
    kind: Literal["instantaneous", "timed", "until_dispelled", "special"]
    amount: int | None = None
    unit: Literal["round", "minute", "hour", "day"] | None = None
    note: str | None = None

    @model_validator(mode="after")
    def check(self):
        if (self.kind == "timed") != (self.amount is not None and self.unit is not None):
            raise ValueError("a timed duration needs amount and unit, and only it has them")
        return self


class Save(Strict):
    ability: Ability
    on_success: Literal["half", "none", "special"]


class Attack(Strict):
    kind: Literal["melee", "ranged"]


class Damage(Strict):
    dice: str
    type: DamageType | None = None
    type_choice: list[DamageType] | None = None  # e.g. Chromatic Orb
    note: str | None = None

    _dice = field_validator("dice")(_check_dice)

    @model_validator(mode="after")
    def check(self):
        if (self.type is None) == (self.type_choice is None):
            raise ValueError("damage needs exactly one of type or type_choice")
        return self


class Healing(Strict):
    dice: str
    temporary: bool = False  # temporary hit points
    note: str | None = None

    _dice = field_validator("dice")(_check_dice)


class HigherSlots(Strict):
    damage_per_level: str | None = None
    healing_per_level: str | None = None
    note: str | None = None

    @field_validator("damage_per_level", "healing_per_level")
    @classmethod
    def dice(cls, value):
        return _check_dice(value) if value is not None else None


class SpellDef(Strict):
    slug: str
    name: str
    level: int = Field(ge=0, le=9)
    school: School
    classes: list[str]
    casting_time: CastingTime
    ritual: bool = False
    range: Range
    area: Area | None = None
    components: Components
    duration: Duration
    concentration: bool = False
    save: Save | None = None
    attack: Attack | None = None
    damage: list[Damage] = []
    healing: Healing | None = None
    cantrip_scaling: dict[Literal[5, 11, 17], str] | None = None
    higher_slots: HigherSlots | None = None
    note: str | None = None
    summary: str  # required, in our own words
    description: str | None = None  # full rules text: only in private packs (copyright)
    page: int | None = None

    @field_validator("cantrip_scaling")
    @classmethod
    def scaling_dice(cls, value):
        return {k: _check_dice(v) for k, v in value.items()} if value else value

    @model_validator(mode="after")
    def check(self):
        if self.cantrip_scaling and self.level != 0:
            raise ValueError("only cantrips have cantrip_scaling")
        if self.higher_slots and self.level == 0:
            raise ValueError("cantrips don't use higher_slots")
        if self.concentration and self.duration.kind != "timed":
            raise ValueError("concentration spells need a timed duration")
        return self

    def details(self) -> dict:
        """The structured fields that go into the spells.details JSON column."""
        data = self.model_dump(
            mode="json",
            exclude_none=True,
            include={
                "casting_time", "range", "area", "components", "duration", "save", "attack",
                "damage", "healing", "cantrip_scaling", "higher_slots", "note", "page",
            },
        )
        return {k: v for k, v in data.items() if v != []}

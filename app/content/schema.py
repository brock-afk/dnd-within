import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.features.schema import (
    Ability,
    DamageType,
    FeatureDef,
    School,
    Slug,
    Text50,
    Text80,
    Text120,
    Text255,
    spends_errors,
)

DICE = re.compile(r"^\s*(\d{1,3}d\d{1,3}(\s*[+-]\s*\d{1,3})?|\d{1,3})\s*$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_dice(value: str) -> str:
    if not DICE.match(value):
        raise ValueError(f"{value!r} isn't dice notation like 3d8 or 1d4+1")
    return value.replace(" ", "")


class PackMeta(Strict):
    slug: Slug
    name: Text120
    kind: Literal["official", "third_party", "homebrew"]
    version: int | str
    requires: list[str] = []


class SkillDef(Strict):
    slug: Slug
    name: Text50
    ability: Ability


class SpeciesDef(Strict):
    slug: Slug
    name: Text50
    summary: Text255
    speed: int = Field(default=30, ge=0, le=120)
    features: list[FeatureDef] = []


class Spellcasting(Strict):
    ability: Ability
    prepared: Annotated[list[int], Field(min_length=20, max_length=20)] | None = None
    ritual_casting: Literal["prepared", "spellbook"] = "prepared"
    slots: Literal["full", "pact"] = "full"


class ClassDef(Strict):
    slug: Slug
    name: Text50
    summary: Text255
    hit_die: Literal[6, 8, 10, 12]
    saving_throws: list[Ability] = Field(min_length=2, max_length=2)
    spellcasting: Spellcasting | None = None
    features: list[FeatureDef] = []


class SubclassDef(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    slug: Slug
    name: Text50
    class_: str = Field(alias="class")
    summary: Text255
    features: list[FeatureDef] = []


class FeatDef(Strict):
    slug: Slug
    name: Text50
    category: Literal["origin", "general"] = "origin"
    summary: Text255
    description: str | None = None
    features: list[FeatureDef] = []


class BackgroundDef(Strict):
    slug: Slug
    name: Text50
    summary: Text255
    description: str | None = None
    feat: str
    features: list[FeatureDef] = []

    @model_validator(mode="after")
    def check(self):
        kinds = [c.kind for f in self.features for c in f.choices]
        if kinds.count("ability_scores") != 1:
            raise ValueError("a background needs exactly one ability_scores choice")
        return self


COST = re.compile(r"^\s*(\d+)\s*(CP|SP|EP|GP|PP)\s*$", re.IGNORECASE)
COPPER = {"CP": 1, "SP": 10, "EP": 50, "GP": 100, "PP": 1000}


class PackItem(Strict):
    item: str
    quantity: int = Field(default=1, ge=1)


class ItemDef(Strict):
    slug: Slug
    name: Text80
    category: Literal["gear", "consumable", "pack", "scroll", "tool", "magic"]
    rarity: Literal["common", "uncommon", "rare", "very_rare", "legendary", "artifact"] | None = (
        None
    )
    cost: str | None = None
    weight: float | None = Field(default=None, ge=0)
    summary: Text255
    description: str | None = None
    consumable: bool = False
    requires_attunement: bool = False
    spell_level: int | None = Field(default=None, ge=0, le=9)
    healing: str | None = None
    contents: list[PackItem] = []
    features: list[FeatureDef] = []

    @field_validator("healing")
    @classmethod
    def check_healing(cls, value):
        return _check_dice(value) if value is not None else None

    @field_validator("cost")
    @classmethod
    def check_cost(cls, value):
        if value is not None and not COST.match(value):
            raise ValueError(f"{value!r} isn't a price like 40 GP or 5 SP")
        return value

    @model_validator(mode="after")
    def check(self):
        if (self.category == "scroll") != (self.spell_level is not None):
            raise ValueError("spell scrolls need spell_level, and only they have one")
        if (self.category == "pack") != bool(self.contents):
            raise ValueError("packs list their contents, and only packs have contents")
        if self.features and self.category in ("pack", "scroll"):
            raise ValueError("packs and scrolls can't have features")
        if problems := spends_errors(self.features):
            raise ValueError("; ".join(problems))
        if self.category in ("consumable", "scroll"):
            self.consumable = True
        return self

    @property
    def cost_cp(self) -> int | None:
        if self.cost is None:
            return None
        amount, coin = COST.match(self.cost).groups()
        return int(amount) * COPPER[coin.upper()]


class CastingTime(Strict):
    unit: Literal["action", "bonus_action", "reaction", "minute", "hour"]
    amount: int = Field(default=1, ge=1)
    trigger: str | None = None

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
    width_feet: int | None = None
    height_feet: int | None = None


class Material(Strict):
    text: str
    cost_gp: int | None = None
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
    type_choice: list[DamageType] | None = None
    note: str | None = None

    _dice = field_validator("dice")(_check_dice)

    @model_validator(mode="after")
    def check(self):
        if (self.type is None) == (self.type_choice is None):
            raise ValueError("damage needs exactly one of type or type_choice")
        return self


class Healing(Strict):
    dice: str
    temporary: bool = False
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


class AcEffectDef(Strict):
    kind: Literal["base", "bonus", "minimum"]
    value: int

    @model_validator(mode="after")
    def check(self):
        if self.kind == "bonus" and self.value == 0:
            raise ValueError("an AC bonus can't be 0")
        if self.kind != "bonus" and not 10 <= self.value <= 30:
            raise ValueError(f"a {self.kind} AC is from 10 to 30")
        return self


class SpellDef(Strict):
    slug: Slug
    name: Text80
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
    ac_effect: AcEffectDef | None = None
    note: str | None = None
    summary: Text255
    description: str | None = None
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
        too_short = self.duration.kind == "instantaneous" or self.duration.unit == "round"
        if self.ac_effect and too_short:
            raise ValueError("ac_effect is for spells lasting a minute or more")
        return self

    def details(self) -> dict:
        data = self.model_dump(
            mode="json",
            exclude_none=True,
            include={
                "casting_time",
                "range",
                "area",
                "components",
                "duration",
                "save",
                "attack",
                "damage",
                "healing",
                "cantrip_scaling",
                "higher_slots",
                "ac_effect",
                "note",
                "page",
            },
        )
        return {k: v for k, v in data.items() if v != []}

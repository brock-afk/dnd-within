import re
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

DICE = re.compile(r"^\d{1,3}d\d{1,3}$")
DICE_BONUS = re.compile(r"^\s*\d{1,3}d\d{1,3}(\s*[+-]\s*\d{1,3})?\s*$")

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=50)]


def _text(length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=length)]


Text50, Text80, Text120, Text255, Text500 = (_text(n) for n in (50, 80, 120, 255, 500))

Ability = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]
DamageType = Literal[
    "acid",
    "bludgeoning",
    "cold",
    "fire",
    "force",
    "lightning",
    "necrotic",
    "piercing",
    "poison",
    "psychic",
    "radiant",
    "slashing",
    "thunder",
]

School = Literal[
    "abjuration",
    "conjuration",
    "divination",
    "enchantment",
    "evocation",
    "illusion",
    "necromancy",
    "transmutation",
]

SPELL_CRITERIA = {"class", "level", "max_level", "school", "ritual", "acquired_via"}


Placement = Literal["senses", "saves", "speed", "resistances", "traits", "none"]


class DamageReactionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["reduce", "retaliate"]
    dice: str
    ability: Ability | None = None
    damage_type: str | None = None

    @model_validator(mode="after")
    def check(self):
        if not DICE.match(self.dice):
            raise ValueError(f"{self.dice!r} isn't dice notation like 1d12")
        return self


class GrantsDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    save_proficiencies: list[Ability] = []
    resistances: list[DamageType] = []
    darkvision: int | None = Field(default=None, ge=5, le=300)
    darkvision_bonus: int | None = Field(default=None, ge=5, le=300)
    speed_bonus: int | None = Field(default=None, ge=5, le=120)
    tool_proficiencies: list[Text50] = []
    ac_bonus: int | None = Field(default=None, ge=1, le=10)

    @model_validator(mode="after")
    def check(self):
        if not self.stored():
            raise ValueError("grants needs at least one attribute")
        return self

    def stored(self) -> dict:
        return self.model_dump(exclude_defaults=True)


class RequiresDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: int | None = Field(default=None, ge=2, le=20)
    option: Slug | None = None

    @model_validator(mode="after")
    def check(self):
        if self.level is None and self.option is None:
            raise ValueError("requires needs a level or an option")
        return self


class OptionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Text80
    summary: Text255
    when: Text120 | None = None
    action: Literal["action", "bonus_action", "reaction"] | None = None
    sheet: Placement | None = None
    damage_reaction: DamageReactionDef | None = None
    grants: GrantsDef | None = None
    requires: RequiresDef | None = None
    features: list[FeatureDef] = []

    @model_validator(mode="after")
    def check_features(self):
        nested = [o.slug for f in self.features for c in f.choices for o in c.options if o.features]
        if nested:
            raise ValueError(
                f"{self.slug}: options inside an option's features can't own features ({nested})"
            )
        if problems := spends_errors(self.features):
            raise ValueError(f"{self.slug}: " + "; ".join(problems))
        return self


class ChoiceDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Text80
    kind: Literal[
        "option", "skill", "expertise", "spell", "spellbook", "subclass", "ability_scores"
    ]
    count: (
        Annotated[int, Field(ge=1)]
        | Annotated[list[Annotated[int, Field(ge=1)]], Field(min_length=20, max_length=20)]
    ) = 1
    level: int = Field(default=1, ge=1, le=20)
    criteria: dict[str, Any] = {}
    options: list[OptionDef] = []
    in_play: bool = False

    @property
    def max_count(self) -> int:
        return max(self.count) if isinstance(self.count, list) else self.count

    @model_validator(mode="after")
    def check_kind(self):
        if isinstance(self.count, list) and self.kind != "option":
            raise ValueError(f"{self.slug}: a count by level is for option choices")
        if self.kind == "option" and len(self.options) < self.max_count:
            raise ValueError(f"{self.slug}: needs at least {self.max_count} options")
        slugs = {o.slug for o in self.options}
        for o in self.options:
            if (
                o.requires
                and o.requires.option
                and (o.requires.option not in slugs or o.requires.option == o.slug)
            ):
                raise ValueError(
                    f"{self.slug} > {o.slug}: requires {o.requires.option!r}, which isn't "
                    "another option of this choice"
                )
        if self.kind != "option" and self.options:
            raise ValueError(f"{self.slug}: only kind 'option' lists its own options")
        if self.in_play and (self.kind != "option" or self.count != 1):
            raise ValueError(f"{self.slug}: in_play is for option choices with count 1")
        if self.kind in ("skill", "expertise") and (
            self.criteria.keys() - {"from"}
            or ("from" in self.criteria and not self.criteria["from"])
        ):
            raise ValueError(
                f"{self.slug}: {self.kind} choices take only criteria {{'from': [skill slugs]}}"
            )
        if self.kind == "ability_scores":
            abilities = self.criteria.get("from")
            valid = get_args(Ability)
            if (
                self.criteria.keys() != {"from"}
                or not isinstance(abilities, list)
                or len(set(abilities)) != 3
                or len(abilities) != 3
                or any(a not in valid for a in abilities)
                or self.count != 1
            ):
                raise ValueError(
                    f"{self.slug}: ability_scores choices need count 1 and criteria "
                    "{'from': [three different abilities]}"
                )
        if self.kind in ("spell", "spellbook"):
            keys = self.criteria.keys()
            if ("level" in keys) == ("max_level" in keys):
                raise ValueError(
                    f"{self.slug}: spell choices need exactly one of criteria 'level' (an exact "
                    "spell level) or 'max_level' (levels 1 up to it)"
                )
            if "class" not in keys and (self.kind == "spellbook" or "max_level" in keys):
                raise ValueError(
                    f"{self.slug}: 'class' is needed for spellbook choices and with 'max_level'"
                )
            if "ritual" in keys and self.criteria["ritual"] is not True:
                raise ValueError(f"{self.slug}: 'ritual' is true (only rituals) or left out")
            if unknown := keys - SPELL_CRITERIA:
                raise ValueError(f"{self.slug}: unknown spell criteria {sorted(unknown)}")
            max_level = self.criteria.get("max_level")
            if (
                max_level is not None
                and max_level != "class_slots"
                and (type(max_level) is not int or not 1 <= max_level <= 9)
            ):
                raise ValueError(
                    f"{self.slug}: max_level is a spell level from 1 to 9, or 'class_slots'"
                )
            if max_level == "class_slots" and self.kind == "spellbook":
                raise ValueError(f"{self.slug}: 'class_slots' is for spell choices only")
            school = self.criteria.get("school")
            if school is not None and school not in get_args(School):
                raise ValueError(f"{self.slug}: unknown school {school!r}")
            via = self.criteria.get("acquired_via")
            if via is not None and (self.kind != "spellbook" or via not in ("level_up", "feature")):
                raise ValueError(
                    f"{self.slug}: 'acquired_via' is for spellbook choices: level_up or feature"
                )
        return self


class UsesDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max: int | Literal["proficiency_bonus"]
    recharge: Literal["short_rest", "long_rest", "dawn"]
    regain: str | None = None

    @model_validator(mode="after")
    def check(self):
        if self.regain is not None:
            if self.recharge != "dawn":
                raise ValueError("regain dice are for charges regained at dawn")
            if not DICE_BONUS.match(self.regain):
                raise ValueError(f"{self.regain!r} isn't dice notation like 1d3 or 1d6+1")
            self.regain = self.regain.replace(" ", "")
        return self


class SlotRecoveryDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget: Literal["half_class_level"]
    max_slot_level: int = Field(ge=1, le=9)


class FeatureSpellDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spell: str
    free_cast: bool = False
    charges: int = Field(default=1, ge=1, le=20)
    always_prepared: bool = True
    note: Text255 | None = None

    @model_validator(mode="after")
    def check(self):
        if not self.always_prepared and not self.free_cast:
            raise ValueError(f"{self.spell}: a spell that isn't prepared must be cast free")
        return self


class SpendsDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: Slug
    amount: int = Field(default=1, ge=1, le=20)


class FeatureDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: Slug
    name: Text80
    summary: Text500
    description: str | None = None
    level: int = Field(default=1, ge=1, le=20)
    applies_to: Literal["all", "starting_class", "multiclass"] = "all"
    uses: UsesDef | None = None
    slot_recovery: SlotRecoveryDef | None = None
    grants: GrantsDef | None = None
    spells: list[FeatureSpellDef] = []
    choices: list[ChoiceDef] = []
    action: Literal["action", "bonus_action", "reaction"] | None = None
    when: Text120 | None = None
    sheet: Placement | None = None
    spends: SpendsDef | None = None

    @model_validator(mode="after")
    def check_spells(self):
        if self.uses is None and any(s.free_cast and s.charges != 1 for s in self.spells):
            raise ValueError(f"{self.slug}: spells cast at will don't spend charges")
        if self.spends and any(s.free_cast for s in self.spells):
            raise ValueError(f"{self.slug}: a feature with spends can't cast spells free")
        return self


def spends_errors(features: list[FeatureDef]) -> list[str]:
    with_uses = {f.slug for f in features if f.uses}
    return [
        f"{f.slug}: spends uses of {f.spends.feature!r}, which isn't a feature here with uses"
        for f in features
        if f.spends and (f.spends.feature not in with_uses or f.spends.feature == f.slug)
    ]


OptionDef.model_rebuild()

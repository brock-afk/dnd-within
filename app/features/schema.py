"""Typed definitions for writing features in code (classes/data.py, species/data.py).

Mistakes in content data fail loudly at startup instead of showing up as broken pages.
"""

import re
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


DICE = re.compile(r"^\d+d\d+$")

# Lowercase words joined by hyphens, like "potent-cantrip". At most 50 characters, the
# smallest slug column.
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=50)]


def _text(length: int):
    """Non-empty text that fits its database column, so an over-long value is reported with
    its file instead of failing the import."""
    return Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=length)]


Text50, Text80, Text120, Text255, Text500 = (_text(n) for n in (50, 80, 120, 255, 500))

Ability = Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"]

School = Literal[
    "abjuration", "conjuration", "divination", "enchantment", "evocation", "illusion",
    "necromancy", "transmutation",
]

# Allowed criteria for spell and spellbook choices.
SPELL_CRITERIA = {"class", "level", "max_level", "school", "acquired_via"}


class DamageReactionDef(BaseModel):
    """Something you can do in reaction to taking damage, offered when damage is entered.

    reduce:    lower the damage by `dice` + `ability` modifier (Stone's Endurance)
    retaliate: hit back for `dice` damage; a reminder, since enemies aren't tracked (Storm's
               Thunder)
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["reduce", "retaliate"]
    dice: str
    ability: Ability | None = None
    damage_type: str | None = None  # retaliate only, e.g. "thunder"

    @model_validator(mode="after")
    def check(self):
        if not DICE.match(self.dice):
            raise ValueError(f"{self.dice!r} isn't dice notation like 1d12")
        return self


class GrantsDef(BaseModel):
    """What having an option picked gives the character, applied on the Play sheet."""

    model_config = ConfigDict(extra="forbid")

    save_proficiencies: list[Ability] = Field(min_length=1)


class OptionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos are errors, not ignored

    slug: Slug
    name: Text80
    summary: Text255
    when: Text120 | None = None  # when it's used, e.g. "Reaction, when you take damage"
    damage_reaction: DamageReactionDef | None = None
    grants: GrantsDef | None = None


class ChoiceDef(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos are errors, not ignored

    slug: Slug
    name: Text80
    kind: Literal["option", "skill", "spell", "spellbook", "subclass"]
    count: int = Field(default=1, ge=1)
    level: int = Field(default=1, ge=1, le=20)  # class/character level the choice unlocks at
    criteria: dict[str, Any] = {}
    options: list[OptionDef] = []
    # Picked and changed on the Play sheet instead of the Build page, for choices that change
    # during play (the Transmuter's Stone benefit). Optional: it can be left unpicked.
    in_play: bool = False

    @model_validator(mode="after")
    def check_kind(self):
        if self.kind == "option" and len(self.options) < self.count:
            raise ValueError(f"{self.slug}: needs at least {self.count} options")
        if self.kind != "option" and self.options:
            raise ValueError(f"{self.slug}: only kind 'option' lists its own options")
        if self.in_play and (self.kind != "option" or self.count != 1):
            raise ValueError(f"{self.slug}: in_play is for option choices with count 1")
        if self.kind == "skill" and not self.criteria.get("from"):
            raise ValueError(f"{self.slug}: skill choices need criteria {{'from': [skill slugs]}}")
        if self.kind in ("spell", "spellbook"):
            keys = self.criteria.keys()
            if "class" not in keys or ("level" in keys) == ("max_level" in keys):
                raise ValueError(
                    f"{self.slug}: spell choices need criteria 'class' and exactly one of "
                    "'level' (an exact spell level) or 'max_level' (levels 1 up to it)"
                )
            if unknown := keys - SPELL_CRITERIA:
                raise ValueError(f"{self.slug}: unknown spell criteria {sorted(unknown)}")
            school = self.criteria.get("school")
            if school is not None and school not in get_args(School):
                raise ValueError(f"{self.slug}: unknown school {school!r}")
            # How a spellbook pick got there: a level up (default) or a feature (Savant).
            via = self.criteria.get("acquired_via")
            if via is not None and (self.kind != "spellbook" or via not in ("level_up", "feature")):
                raise ValueError(
                    f"{self.slug}: 'acquired_via' is for spellbook choices: level_up or feature"
                )
        return self


class UsesDef(BaseModel):
    """A feature you can use a limited number of times between rests."""

    model_config = ConfigDict(extra="forbid")

    max: int | Literal["proficiency_bonus"]
    recharge: Literal["short_rest", "long_rest"]


class SlotRecoveryDef(BaseModel):
    """Recover expended spell slots during a short rest (the Wizard's Arcane Recovery)."""

    model_config = ConfigDict(extra="forbid")

    budget: Literal["half_class_level"]  # total slot levels: half the class level, rounded up
    max_slot_level: int = Field(ge=1, le=9)


class FeatureDef(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos are errors, not ignored

    slug: Slug
    name: Text80
    summary: Text500  # required, in our own words
    description: str | None = None  # full rules text: only in private packs and homebrew
    level: int = Field(default=1, ge=1, le=20)
    applies_to: Literal["all", "starting_class", "multiclass"] = "all"
    uses: UsesDef | None = None
    slot_recovery: SlotRecoveryDef | None = None
    choices: list[ChoiceDef] = []

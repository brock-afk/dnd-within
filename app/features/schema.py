"""Typed definitions for writing features in code (classes/data.py, species/data.py).

Mistakes in content data fail loudly at startup instead of showing up as broken pages.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DICE = re.compile(r"^\d+d\d+$")


class DamageReactionDef(BaseModel):
    """Something you can do in reaction to taking damage, offered when damage is entered.

    reduce:    lower the damage by `dice` + `ability` modifier (Stone's Endurance)
    retaliate: hit back for `dice` damage; a reminder, since enemies aren't tracked (Storm's
               Thunder)
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["reduce", "retaliate"]
    dice: str
    ability: Literal["STR", "DEX", "CON", "INT", "WIS", "CHA"] | None = None
    damage_type: str | None = None  # retaliate only, e.g. "thunder"

    @model_validator(mode="after")
    def check(self):
        if not DICE.match(self.dice):
            raise ValueError(f"{self.dice!r} isn't dice notation like 1d12")
        return self


class OptionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos are errors, not ignored

    slug: str
    name: str
    summary: str
    when: str | None = None  # when it's used, e.g. "Reaction, when you take damage"
    damage_reaction: DamageReactionDef | None = None


class ChoiceDef(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos are errors, not ignored

    slug: str
    name: str
    kind: Literal["option", "skill", "spell", "spellbook", "subclass"]
    count: int = Field(default=1, ge=1)
    level: int = Field(default=1, ge=1, le=20)  # class/character level the choice unlocks at
    criteria: dict[str, Any] = {}
    options: list[OptionDef] = []

    @model_validator(mode="after")
    def check_kind(self):
        if self.kind == "option" and len(self.options) < self.count:
            raise ValueError(f"{self.slug}: needs at least {self.count} options")
        if self.kind != "option" and self.options:
            raise ValueError(f"{self.slug}: only kind 'option' lists its own options")
        if self.kind == "skill" and not self.criteria.get("from"):
            raise ValueError(f"{self.slug}: skill choices need criteria {{'from': [skill slugs]}}")
        if self.kind in ("spell", "spellbook"):
            keys = self.criteria.keys()
            if "class" not in keys or ("level" in keys) == ("max_level" in keys):
                raise ValueError(
                    f"{self.slug}: spell choices need criteria 'class' and exactly one of "
                    "'level' (an exact spell level) or 'max_level' (levels 1 up to it)"
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

    slug: str
    name: str
    summary: str
    level: int = Field(default=1, ge=1, le=20)
    applies_to: Literal["all", "starting_class", "multiclass"] = "all"
    uses: UsesDef | None = None
    slot_recovery: SlotRecoveryDef | None = None
    choices: list[ChoiceDef] = []

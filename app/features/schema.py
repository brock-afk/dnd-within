"""Typed definitions for writing features in code (classes/data.py, species/data.py).

Mistakes in content data fail loudly at startup instead of showing up as broken pages.
"""

import re
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# At most three digits per number (999d999+999), so a roll stays cheap.
DICE = re.compile(r"^\d{1,3}d\d{1,3}$")
DICE_BONUS = re.compile(r"^\s*\d{1,3}d\d{1,3}(\s*[+-]\s*\d{1,3})?\s*$")  # "1d3", "1d6 + 1"

# Lowercase words joined by hyphens, like "potent-cantrip". At most 50 characters, the
# smallest slug column.
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=50)]


def _text(length: int):
    """Non-empty text that fits its database column, so an over-long value is reported with
    its file instead of failing the import."""
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
    """Character attributes a feature gives (always), or an option gives (while picked).
    The Play sheet lists each with where it comes from.

    darkvision:       a range; the highest source wins (a species' Darkvision 60)
    darkvision_bonus: added on top, or from 0 without Darkvision (the Transmuter's Stone)
    tool_proficiencies: tool names, e.g. "Thieves' Tools" or a picked "Playing Cards"
    ac_bonus:         added to AC (a magic item's +1)
    """

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
        """What goes in the grants JSON columns: only what's set."""
        return self.model_dump(exclude_defaults=True)


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
    kind: Literal[
        "option", "skill", "expertise", "spell", "spellbook", "subclass", "ability_scores"
    ]
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
        # Without `from`, a skill choice offers any skill: a background's free pick, or for
        # Expertise any skill the character is proficient in (Rogue, Bard).
        if self.kind in ("skill", "expertise") and (
            self.criteria.keys() - {"from"}
            or ("from" in self.criteria and not self.criteria["from"])
        ):
            raise ValueError(
                f"{self.slug}: {self.kind} choices take only criteria {{'from': [skill slugs]}}"
            )
        if self.kind == "ability_scores":
            # A background's increases: +2 to one of these and +1 to another, or +1 to all three.
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
    """A feature you can use a limited number of times between rests, or a magic item's
    charges. "dawn" is a long rest on the sheet; with `regain` dice ("1d3") a long rest rolls
    them and gives back that many instead of all."""

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
    """Recover expended spell slots during a short rest (the Wizard's Arcane Recovery)."""

    model_config = ConfigDict(extra="forbid")

    budget: Literal["half_class_level"]  # total slot levels: half the class level, rounded up
    max_slot_level: int = Field(ge=1, le=9)


class FeatureSpellDef(BaseModel):
    """A spell a feature gives you (Wondrous Alteration's Alter Self, a magic item's spell)."""

    model_config = ConfigDict(extra="forbid")

    spell: str  # spell slug, e.g. "alter-self" or "phb-2024/alter-self"
    # A cast can spend `charges` uses of the feature instead of a spell slot.
    free_cast: bool = False
    charges: int = Field(default=1, ge=1, le=20)
    # Also castable with spell slots, like any prepared spell. Off for a magic item's spell that
    # can only be cast by spending its charges.
    always_prepared: bool = True
    note: Text255 | None = None  # shown on the spell, e.g. what the feature adds to it

    @model_validator(mode="after")
    def check(self):
        if not self.always_prepared and not self.free_cast:
            raise ValueError(f"{self.spell}: a spell that isn't prepared must be cast with uses")
        return self


class SpendsDef(BaseModel):
    """Using this feature spends uses of another feature from the same source (Stonecunning
    spends one of the item's charges)."""

    model_config = ConfigDict(extra="forbid")

    feature: Slug  # a sibling feature's slug; it must have uses
    amount: int = Field(default=1, ge=1, le=20)


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
    grants: GrantsDef | None = None  # always on while the character has the feature
    spells: list[FeatureSpellDef] = []
    choices: list[ChoiceDef] = []
    # Something you do: what it takes, and the uses it spends. The sheet offers Use for it.
    action: Literal["action", "bonus_action", "reaction"] | None = None
    spends: SpendsDef | None = None

    @model_validator(mode="after")
    def check_spells(self):
        if any(s.free_cast for s in self.spells) and self.uses is None:
            raise ValueError(
                f"{self.slug}: free_cast spells spend the feature's uses, so it needs uses"
            )
        return self


def spends_errors(features: list[FeatureDef]) -> list[str]:
    """Problems with features' `spends`: each must name a sibling feature that has uses."""
    with_uses = {f.slug for f in features if f.uses}
    return [
        f"{f.slug}: spends uses of {f.spends.feature!r}, which isn't a feature here with uses"
        for f in features
        if f.spends and (f.spends.feature not in with_uses or f.spends.feature == f.slug)
    ]

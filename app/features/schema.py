"""Typed definitions for writing features in code (classes/data.py, species/data.py).

Mistakes in content data fail loudly at startup instead of showing up as broken pages.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class OptionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos are errors, not ignored

    slug: str
    name: str
    summary: str


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


class FeatureDef(BaseModel):
    model_config = ConfigDict(extra="forbid")  # typos are errors, not ignored

    slug: str
    name: str
    summary: str
    level: int = Field(default=1, ge=1, le=20)
    applies_to: Literal["all", "starting_class", "multiclass"] = "all"
    choices: list[ChoiceDef] = []

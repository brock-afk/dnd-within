"""Typed definitions for writing features in code (classes/data.py, species/data.py).

Mistakes in content data fail loudly at startup instead of showing up as broken pages.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class OptionDef(BaseModel):
    slug: str
    name: str
    summary: str


class ChoiceDef(BaseModel):
    slug: str
    name: str
    kind: Literal["option", "skill", "spell"]
    count: int = Field(default=1, ge=1)
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
        if self.kind == "spell" and {"class", "level"} - self.criteria.keys():
            raise ValueError(f"{self.slug}: spell choices need criteria {{'class', 'level'}}")
        return self


class FeatureDef(BaseModel):
    slug: str
    name: str
    summary: str
    level: int = Field(default=1, ge=1, le=20)
    choices: list[ChoiceDef] = []

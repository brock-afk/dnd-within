"""A character's species and background: picked the same way, from one shared form, so each is
described here and the queries, page and service work for both."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.backgrounds.models import Background
from app.species.models import Species


@dataclass(frozen=True)
class Origin:
    model: type[Background] | type[Species]
    name: str  # the Character column is <name>_id, the routes /characters/{id}/<name>
    detail: Callable[[Any], str]  # the line under a row's name in the picker

    @property
    def column(self) -> str:
        return f"{self.name}_id"

    @property
    def title(self) -> str:
        return self.name.capitalize()


BACKGROUND = Origin(Background, "background", lambda b: f"Origin feat: {b.feat.name}")
SPECIES = Origin(Species, "species", lambda s: f"Speed {s.speed} ft")

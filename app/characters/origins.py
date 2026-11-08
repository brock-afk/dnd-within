from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.backgrounds.models import Background
from app.species.models import Species


@dataclass(frozen=True)
class Origin:
    model: type[Background] | type[Species]
    name: str
    detail: Callable[[Any], str]

    @property
    def column(self) -> str:
        return f"{self.name}_id"

    @property
    def title(self) -> str:
        return self.name.capitalize()


BACKGROUND = Origin(Background, "background", lambda b: f"Origin feat: {b.feat.name}")
SPECIES = Origin(Species, "species", lambda s: f"Speed {s.speed} ft")

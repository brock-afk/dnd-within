from pydantic import BaseModel

from app.abilities.rules import METHODS, Ability, point_buy_step
from app.core.forms import parse_int


class AbilityForm(BaseModel):
    method: str = ""
    strength: str = ""
    dexterity: str = ""
    constitution: str = ""
    intelligence: str = ""
    wisdom: str = ""
    charisma: str = ""
    rolls: list[str] = []
    step: str = ""
    reset: str = ""

    @property
    def editor_method(self) -> str:
        return self.method if self.method in METHODS else "standard_array"

    def scores(self) -> dict[str, int | None]:
        return {a.column: parse_int(getattr(self, a.column)) for a in Ability}

    def roll_values(self) -> list[int | None]:
        rolls = [parse_int(r) for r in self.rolls[:6]]
        return rolls + [None] * (6 - len(rolls))

    def previewed_scores(self) -> dict[str, int | None]:
        scores = self.scores()
        if self.reset:
            scores = dict.fromkeys(scores)
        if self.editor_method == "point_buy":
            scores = {column: score or 8 for column, score in scores.items()}
            column, _, delta = self.step.partition(":")
            if column in scores and delta in ("1", "-1"):
                point_buy_step(scores, column, int(delta))
        return scores


class IncreaseForm(BaseModel):
    split: str = "uneven"
    plus2: str = ""
    plus1: str = ""
    changed: str = ""

    def resolve_clash(self) -> None:
        if self.plus2 and self.plus2 == self.plus1:
            if self.changed == "plus2":
                self.plus1 = ""
            else:
                self.plus2 = ""

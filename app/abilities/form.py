from pydantic import BaseModel

from app.abilities.rules import ABILITIES, METHODS, point_buy_step
from app.core.forms import parse_int


class AbilityForm(BaseModel):
    method: str = ""
    strength: str = ""
    dexterity: str = ""
    constitution: str = ""
    intelligence: str = ""
    wisdom: str = ""
    charisma: str = ""
    rolls: list[str] = []  # manual entry: the six rolled numbers
    step: str = ""  # point buy: "<column>:1" or "<column>:-1" from a stepper button
    reset: str = ""  # set by the Reset button

    @property
    def editor_method(self) -> str:
        """The tab to show it on: the submitted method, or the standard array's."""
        return self.method if self.method in METHODS else "standard_array"

    def scores(self) -> dict[str, int | None]:
        """Keyed by column. Blank or non-numeric becomes None, and so does anything over
        parse_int's four digits. No range check here, so rules.validate reports a score like
        100 as out of range, not as missing."""
        return {a.column: parse_int(getattr(self, a.column)) for a in ABILITIES}

    def roll_values(self) -> list[int | None]:
        """The six rolled numbers for manual entry, padded to six."""
        rolls = [parse_int(r) for r in self.rolls[:6]]
        return rolls + [None] * (6 - len(rolls))

    def previewed_scores(self) -> dict[str, int | None]:
        """The scores after a Reset or stepper click."""
        scores = self.scores()
        if self.reset:
            # Back to a fresh tab: point buy starts every score at 8, the others clear the
            # assignments. Manual entry keeps the rolls, since those came from real dice.
            scores = dict.fromkeys(scores)
        if self.editor_method == "point_buy":
            scores = {column: score or 8 for column, score in scores.items()}
            column, _, delta = self.step.partition(":")
            if column in scores and delta in ("1", "-1"):
                point_buy_step(scores, column, int(delta))
        return scores


class IncreaseForm(BaseModel):
    split: str = "uneven"  # "uneven" (+2 and +1) or "even" (+1 to each)
    plus2: str = ""
    plus1: str = ""
    changed: str = ""  # preview: which column was just clicked, "plus2" or "plus1"

    def resolve_clash(self) -> None:
        """One ability can't take both: the column just clicked wins, the other is cleared."""
        if self.plus2 and self.plus2 == self.plus1:
            if self.changed == "plus2":
                self.plus1 = ""
            else:
                self.plus2 = ""

from enum import StrEnum


class Action(StrEnum):
    ACTION = "action"
    BONUS_ACTION = "bonus_action"
    REACTION = "reaction"

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

from enum import StrEnum


class LabeledEnum(StrEnum):
    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

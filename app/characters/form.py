from pydantic import BaseModel, ConfigDict


class CharacterForm(BaseModel):
    """The new-character form, kept as typed so a failed create can show it again."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = ""
    class_id: int | None = None
    species_id: int | None = None

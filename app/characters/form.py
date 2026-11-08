from pydantic import BaseModel, ConfigDict


class CharacterForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = ""
    class_id: int | None = None
    species_id: int | None = None

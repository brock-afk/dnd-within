from typing import Annotated

from fastapi import Depends

from app.characters.dependencies import OwnedCharacter, owned_child
from app.core.db import DbSession
from app.sheet.models import CharacterAcEffect, CharacterHpEffect


def get_hp_effect(effect_id: int, db: DbSession, character: OwnedCharacter) -> CharacterHpEffect:
    return owned_child(db, CharacterHpEffect, effect_id, character)


def get_ac_effect(effect_id: int, db: DbSession, character: OwnedCharacter) -> CharacterAcEffect:
    return owned_child(db, CharacterAcEffect, effect_id, character)


OwnedHpEffect = Annotated[CharacterHpEffect, Depends(get_hp_effect)]
OwnedAcEffect = Annotated[CharacterAcEffect, Depends(get_ac_effect)]

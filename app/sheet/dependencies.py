from typing import Annotated

from fastapi import Depends, HTTPException

from app.characters.dependencies import OwnedCharacter, owned_child
from app.core.db import DbSession
from app.sheet.models import CharacterAcEffect, CharacterHpEffect
from app.sheet.queries import copyable
from app.spells.models import Spell


def get_hp_effect(effect_id: int, db: DbSession, character: OwnedCharacter) -> CharacterHpEffect:
    return owned_child(db, CharacterHpEffect, effect_id, character)


def get_ac_effect(effect_id: int, db: DbSession, character: OwnedCharacter) -> CharacterAcEffect:
    return owned_child(db, CharacterAcEffect, effect_id, character)


OwnedHpEffect = Annotated[CharacterHpEffect, Depends(get_hp_effect)]
OwnedAcEffect = Annotated[CharacterAcEffect, Depends(get_ac_effect)]


def get_copyable_spell(db: DbSession, spell: str = "") -> Spell:
    found = copyable(db, spell)
    if found is None:
        raise HTTPException(status_code=404)
    return found


CopyableSpell = Annotated[Spell, Depends(get_copyable_spell)]

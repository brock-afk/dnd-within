from typing import Annotated

from fastapi import Depends, HTTPException

from app.characters.dependencies import OwnedCharacter, owned_child
from app.core.db import DbSession
from app.sheet.models import CharacterAcEffect, CharacterHpEffect
from app.sheet.queries import FeatureUses, Spender, copyable, spender, uses_of
from app.spells.models import Spell


def get_hp_effect(effect_id: int, db: DbSession, character: OwnedCharacter) -> CharacterHpEffect:
    return owned_child(db, CharacterHpEffect, effect_id, character)


def get_ac_effect(effect_id: int, db: DbSession, character: OwnedCharacter) -> CharacterAcEffect:
    return owned_child(db, CharacterAcEffect, effect_id, character)


OwnedHpEffect = Annotated[CharacterHpEffect, Depends(get_hp_effect)]
OwnedAcEffect = Annotated[CharacterAcEffect, Depends(get_ac_effect)]


def get_copyable_spell(db: DbSession, character: OwnedCharacter, spell: str = "") -> Spell:
    found = copyable(db, spell, character.user_id)
    if found is None:
        raise HTTPException(status_code=404)
    return found


CopyableSpell = Annotated[Spell, Depends(get_copyable_spell)]


def get_feature_uses(feature_id: int, db: DbSession, character: OwnedCharacter) -> FeatureUses:
    uses = uses_of(db, character, feature_id)
    if uses is None:
        raise HTTPException(status_code=404)
    return uses


def get_tracked_uses(uses: Annotated[FeatureUses, Depends(get_feature_uses)]) -> FeatureUses:
    if uses.rest_only:
        raise HTTPException(status_code=404)
    return uses


def get_recovery_uses(uses: Annotated[FeatureUses, Depends(get_feature_uses)]) -> FeatureUses:
    if not uses.rest_only:
        raise HTTPException(status_code=404)
    return uses


TrackedUses = Annotated[FeatureUses, Depends(get_tracked_uses)]
RecoveryUses = Annotated[FeatureUses, Depends(get_recovery_uses)]


def get_spender(feature_id: int, db: DbSession, character: OwnedCharacter) -> Spender:
    found = spender(db, character, feature_id)
    if found is None:
        raise HTTPException(status_code=404)
    return found


UsesSpender = Annotated[Spender, Depends(get_spender)]

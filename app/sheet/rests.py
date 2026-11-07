"""Short and long rests (2024 rules). Generic: nothing here knows about a specific class;
features declare `uses` and `slot_recovery` in their content."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.features.models import Feature
from app.sheet.models import (
    CharacterAcEffect,
    CharacterFeatureUse,
    CharacterHitDice,
    CharacterHpEffect,
    CharacterSpellSlot,
)
from app.sheet.queries import feature_uses
from app.sheet.rules import roll, uses_maximum
from app.sheet.service import play_state


def spend_hit_die(db: Session, character: Character, class_id: int) -> None:
    row = db.get(CharacterHitDice, (character.id, class_id))
    if row is None:
        row = CharacterHitDice(character_id=character.id, class_id=class_id, spent=0)
        db.add(row)
    row.spent += 1


# --- Rests --------------------------------------------------------------------------------


def finish_short_rest(db: Session, character: Character) -> None:
    """Restore every use that recharges on a short rest, and every Pact Magic slot."""
    db.execute(
        delete(CharacterSpellSlot).where(
            CharacterSpellSlot.character_id == character.id, CharacterSpellSlot.kind == "pact"
        )
    )
    for uses in feature_uses(db, character):
        if uses.recharge == "short_rest":
            db.execute(
                delete(CharacterFeatureUse).where(
                    CharacterFeatureUse.character_id == character.id,
                    CharacterFeatureUse.feature_id == uses.feature.id,
                )
            )


def long_rest(db: Session, character: Character) -> None:
    """Full HP, no temporary HP, every hit die back (2024 rules), all spell slots and every
    feature use restored, and AC spells cast from the sheet ended. Every max HP effect ends: a
    reduced max returns to normal, and effects like Aid (8 hours) are over.

    Charges regained "at dawn" count as a long rest. Ones that regain a roll (1d3) get that
    many back instead of all."""
    db.execute(delete(CharacterHpEffect).where(CharacterHpEffect.character_id == character.id))
    state = play_state(db, character)
    state.current_hp = None  # at full, of the restored max
    state.temp_hp = 0
    state.temp_hp_source = None
    # Every spent-uses row, not just active features': an item regains its charges at dawn
    # whether or not it's attuned.
    for row, feature in db.execute(
        select(CharacterFeatureUse, Feature)
        .join(Feature, Feature.id == CharacterFeatureUse.feature_id)
        .where(CharacterFeatureUse.character_id == character.id)
    ):
        regain = (feature.uses or {}).get("regain")
        if regain:
            # A negative roll (1d3-2) regains nothing; a rest never spends charges.
            regained = max(0, roll(regain))
            row.expended = max(
                0, min(row.expended, uses_maximum(feature.uses["max"], character.level)) - regained
            )
        else:
            db.delete(row)
    for model in (CharacterHitDice, CharacterSpellSlot):
        db.execute(delete(model).where(model.character_id == character.id))
    # Spells like Mage Armor (8 hours) are over; AC effects added by hand stay.
    db.execute(
        delete(CharacterAcEffect).where(
            CharacterAcEffect.character_id == character.id,
            CharacterAcEffect.ends_on_long_rest.is_(True),
        )
    )

from sqlalchemy.orm import Session

from app.characters.models import Character
from app.features.service import fill_fixed_choices, remove_inapplicable_picks
from app.sheet.service import max_hp, track_max_change


def change_origin(db: Session, character: Character, column: str, row_id: int) -> None:
    """Switch the character's species or background (`column` is "species_id" or
    "background_id"). Picks for the old one's features go with it, choices the new one fills
    by itself are made, and current HP follows any max HP change (a Constitution increase).
    Commits."""
    old_max = max_hp(db, character)
    setattr(character, column, row_id)
    db.flush()
    db.refresh(character)  # reload the relationship the rules below read
    remove_inapplicable_picks(db, character)
    db.commit()
    fill_fixed_choices(db, character)
    track_max_change(db, character, old_max, heal=True)
    db.commit()

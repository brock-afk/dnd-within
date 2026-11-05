from sqlalchemy.orm import Session

from app.auth.models import User
from app.characters.form import CharacterForm
from app.characters.models import Character
from app.classes.models import CharacterClass, CharacterClassLevel
from app.content.queries import available_row
from app.features.service import fill_fixed_choices, remove_inapplicable_picks
from app.leveling.models import CharacterLevel
from app.sheet.service import tracking_max_hp
from app.species.models import Species


def _name_error(name: str) -> str | None:
    if not name:
        return "Give your character a name."
    if len(name) > 60:
        return "Names can be at most 60 characters."
    return None


def create_character(
    db: Session, user: User, form: CharacterForm
) -> tuple[Character | None, dict[str, str]]:
    """A level 1 character in the chosen class and species, or (None, {field: problem}) with
    nothing saved."""
    errors = {}
    if error := _name_error(form.name):
        errors["name"] = error
    if available_row(db, CharacterClass, form.class_id) is None:
        errors["class_id"] = "Choose a class."
    if available_row(db, Species, form.species_id) is None:
        errors["species_id"] = "Choose a species."
    if errors:
        return None, errors
    character = Character(
        user_id=user.id,
        name=form.name,
        species_id=form.species_id,
        classes=[CharacterClassLevel(class_id=form.class_id, position=0)],
        levels=[CharacterLevel(character_level=1, class_id=form.class_id, hp_method="max")],
    )
    db.add(character)
    db.flush()
    return character, {}


def rename(character: Character, name: str) -> str | None:
    name = name.strip()
    if error := _name_error(name):
        return error
    character.name = name
    return None


def delete_character(db: Session, character: Character, confirm: str) -> str | None:
    if confirm.strip().lower() != "delete":
        return "Type delete to confirm."
    # Classes, skills, spells and choice picks are removed by ON DELETE CASCADE.
    db.delete(character)
    db.flush()
    return None


def change_origin(db: Session, character: Character, column: str, row_id: int) -> None:
    """Switch the character's species or background (`column` is "species_id" or
    "background_id"). Picks for the old one's features go with it, choices the new one fills
    by itself are made, and current HP follows any max HP change (a Constitution increase)."""
    with tracking_max_hp(db, character, heal=True):
        setattr(character, column, row_id)
        db.flush()
        db.refresh(character)  # reload the relationship the rules below read
        remove_inapplicable_picks(db, character)
        fill_fixed_choices(db, character)

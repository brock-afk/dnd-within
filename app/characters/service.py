from sqlalchemy.orm import Session

from app.auth.models import User
from app.characters.form import CharacterForm
from app.characters.models import Character
from app.characters.origins import Origin
from app.classes.models import CharacterClass, CharacterClassLevel
from app.content.queries import available_row
from app.core.forms import parse_id
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
    db.delete(character)
    db.flush()
    return None


def choose_origin(db: Session, character: Character, origin: Origin, key: str) -> str | None:
    row_id = parse_id(key)
    if row_id is not None and row_id == getattr(character, origin.column):
        return None
    row = available_row(db, origin.model, row_id)
    if row is None:
        return f"Choose a {origin.title.lower()}."
    with tracking_max_hp(db, character, heal=True):
        setattr(character, origin.column, row.id)
        db.flush()
        db.refresh(character)
        remove_inapplicable_picks(db, character)
        fill_fixed_choices(db, character)
    return None

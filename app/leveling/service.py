"""Adding and removing levels. Each operation returns an error message with nothing changed,
or None once it's done. They flush, never commit."""

from sqlalchemy.orm import Session

from app.characters.models import Character
from app.core.forms import parse_amount, parse_id
from app.features.service import remove_inapplicable_picks
from app.leveling.models import CharacterLevel
from app.leveling.queries import constitution_modifier, starting_class
from app.leveling.rules import MAX_LEVEL
from app.sheet.service import tracking_max_hp

# From a second tab, or a click landing after another took effect: acting on the current level
# would add or remove one the user didn't see.
STALE = "This page was out of date. It now shows the character's current level."


def level_up(
    db: Session, character: Character, shown: str, hp_method: str, hp_roll: str
) -> str | None:
    """Add the level after `shown`, the level the page showed. Its hit points are the fixed
    value or a roll; current HP rises with the max."""
    starting = starting_class(character)
    die = starting.hit_die
    roll = parse_amount(hp_roll, 1, die) if hp_method == "rolled" else None
    if parse_id(shown) != character.level:
        return STALE
    if character.level >= MAX_LEVEL:
        return f"Level {MAX_LEVEL} is the maximum."
    if constitution_modifier(db, character) is None:
        return "Set ability scores first: hit points depend on Constitution."
    if hp_method not in ("fixed", "rolled"):
        return "Choose the fixed value or enter a roll."
    if hp_method == "rolled" and roll is None:
        return f"Enter your d{die} roll, from 1 to {die}."
    with tracking_max_hp(db, character, heal=True):
        character.levels.append(
            CharacterLevel(
                character_level=character.level + 1,
                class_id=starting.id,
                hp_method=hp_method,
                hp_roll=roll,
            )
        )
    return None


def level_down(db: Session, character: Character, shown: str) -> str | None:
    """Remove level `shown`, the last one, with picks for features from that level. Current HP
    is capped at the new max."""
    if parse_id(shown) != character.level:
        return STALE
    if character.level <= 1:
        return "Level 1 can't be removed."
    # The picks go inside the block too: one may have raised Constitution.
    with tracking_max_hp(db, character, heal=False):
        character.levels.remove(character.levels[-1])
        db.flush()
        remove_inapplicable_picks(db, character)
    return None

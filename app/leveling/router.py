from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.core.db import DbSession
from app.core.templates import hx_redirect, templates
from app.features.service import remove_inapplicable_picks
from app.leveling.models import CharacterLevel
from app.leveling.rules import MAX_LEVEL, fixed_hp, level_hp
from app.leveling.service import constitution_modifier

router = APIRouter(tags=["leveling"])


def _render_panel(request, db, character: Character, roll: str = "", error=None, status_code=200):
    # Single class until multiclassing: every level goes to the starting class.
    starting = character.classes[0]
    die = starting.character_class.hit_die
    con_mod = constitution_modifier(db, character)
    fixed = fixed_hp(die)
    return templates.TemplateResponse(
        request,
        "leveling/partials/level_up.html",
        {
            "character": character,
            "class_name": starting.character_class.name,
            "next_level": character.level + 1,
            "at_max": character.level >= MAX_LEVEL,
            "hit_die": die,
            "con_mod": con_mod,
            "fixed": fixed,
            "fixed_gain": level_hp(fixed, con_mod) if con_mod is not None else None,
            "roll": roll,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/characters/{character_id}/level-up", response_class=HTMLResponse)
def level_up_panel(request: Request, db: DbSession, character: OwnedCharacter):
    return _render_panel(request, db, character)


@router.post("/characters/{character_id}/level-up")
def level_up(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    hp_method: Annotated[str, Form()] = "",
    hp_roll: Annotated[str, Form()] = "",
):
    starting = character.classes[0]
    die = starting.character_class.hit_die
    roll = hp_roll.strip()

    error = None
    if character.level >= MAX_LEVEL:
        error = f"Level {MAX_LEVEL} is the maximum."
    elif constitution_modifier(db, character) is None:
        error = "Set ability scores first: hit points depend on Constitution."
    elif hp_method not in ("fixed", "rolled"):
        error = "Choose the fixed value or enter a roll."
    elif hp_method == "rolled" and not (roll.isdigit() and 1 <= int(roll) <= die):
        error = f"Enter your d{die} roll, from 1 to {die}."
    if error:
        return _render_panel(request, db, character, roll, error, status_code=400)

    character.levels.append(
        CharacterLevel(
            character_level=character.level + 1,
            class_id=starting.class_id,
            hp_method=hp_method,
            hp_roll=int(roll) if hp_method == "rolled" else None,
        )
    )
    db.commit()
    return hx_redirect(f"/characters/{character.id}")


@router.post("/characters/{character_id}/level-down")
def level_down(db: DbSession, character: OwnedCharacter):
    if character.level <= 1:
        return HTMLResponse("Level 1 can't be removed.", status_code=400)
    character.levels.remove(character.levels[-1])
    db.flush()
    # Features from the removed level are gone, so their picks go too.
    remove_inapplicable_picks(db, character)
    db.commit()
    return hx_redirect(f"/characters/{character.id}")

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import delete

from app.auth.dependencies import CurrentUser
from app.auth.models import User
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.core.db import DbSession
from app.core.templates import morph_in_place, templates
from app.features.kinds import KINDS
from app.sheet.models import CharacterHpEffect, CharacterPreparedSpell
from app.sheet.rules import heal, set_temp_hp, take_damage
from app.sheet.service import (
    castable_spells,
    hp_view,
    max_hp,
    play_state,
    prepared_limit,
    prepared_spell_ids,
    track_max_change,
)
from app.spells.queries import spellbook

router = APIRouter(tags=["sheet"])

SHEET_SELECTOR = "#sheet-page"


def render_sheet(request, db, user: User, character: Character, errors=None, status_code=200):
    return templates.TemplateResponse(
        request,
        "sheet/sheet.html",
        {
            "user": user,
            "character": character,
            "hp": hp_view(db, character),
            "castable": castable_spells(db, character),
            "prepared_count": len(prepared_spell_ids(db, character)),
            "prepared_limit": prepared_limit(character),
            "has_spellbook": bool(spellbook(db, character.id)),
            "errors": errors or {},
        },
        status_code=status_code,
    )


def refresh_sheet(request, db, user, character, errors=None, status_code=200):
    """Re-render the sheet and morph it into place (see app/core/templates.py)."""
    db.expire_all()  # sessions don't expire on commit; reload what just changed
    response = render_sheet(request, db, user, character, errors, status_code)
    return morph_in_place(response, SHEET_SELECTOR)


def _amount(raw: str, low: int, high: int) -> int | None:
    raw = raw.strip()
    if raw.lstrip("-").isdigit() and low <= int(raw) <= high:
        return int(raw)
    return None


@router.get("/characters/{character_id}/sheet", response_class=HTMLResponse)
def show_sheet(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    return render_sheet(request, db, user, character)


# --- Hit points ---------------------------------------------------------------------------


@router.post("/characters/{character_id}/sheet/hp", response_class=HTMLResponse)
def change_hp(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    action: Annotated[str, Form()] = "",
    amount: Annotated[str, Form()] = "",
):
    maximum = max_hp(db, character)
    value = _amount(amount, 0, 999)
    if maximum is None or action not in ("damage", "heal") or value is None:
        errors = {"hp": "Enter a whole number from 0 to 999."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)
    state = play_state(db, character)
    (take_damage if action == "damage" else heal)(state, value, maximum)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post("/characters/{character_id}/sheet/temp-hp", response_class=HTMLResponse)
def change_temp_hp(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    amount: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "",
):
    value = _amount(amount, 0, 999)
    if value is None:
        errors = {"temp_hp": "Enter a whole number from 0 to 999."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)
    set_temp_hp(play_state(db, character), value, source.strip()[:80])
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post("/characters/{character_id}/sheet/hp-effects", response_class=HTMLResponse)
def add_hp_effect(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    label: Annotated[str, Form()] = "",
    delta: Annotated[str, Form()] = "",
):
    value = _amount(delta, -999, 999)
    label = label.strip()[:80]
    if not label or not value:
        errors = {"effect": "Give the effect a name and a non-zero amount (e.g. Aid, +5)."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)
    old_max = max_hp(db, character)
    db.add(CharacterHpEffect(character_id=character.id, label=label, max_hp_delta=value))
    # Starting an effect like Aid heals by the increase; a drain only caps current HP.
    track_max_change(db, character, old_max, heal=value > 0)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post(
    "/characters/{character_id}/sheet/hp-effects/{effect_id}/end", response_class=HTMLResponse
)
def end_hp_effect(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, effect_id: int
):
    effect = db.get(CharacterHpEffect, effect_id)
    if effect is None or effect.character_id != character.id:
        raise HTTPException(status_code=404)
    old_max = max_hp(db, character)
    db.delete(effect)
    # Ending an effect never heals: Aid ending only caps current HP, and a drain wearing off
    # raises max HP without restoring any.
    track_max_change(db, character, old_max, heal=False)
    db.commit()
    return refresh_sheet(request, db, user, character)


# --- Prepared spells ----------------------------------------------------------------------


def _render_prepared_editor(request, db, character, selected, error=None, status_code=200):
    options = [KINDS["spell"].view(entry.spell) for entry in spellbook(db, character.id)]
    return templates.TemplateResponse(
        request,
        "sheet/partials/prepared_editor.html",
        {
            "character": character,
            "options": options,
            "selected": selected,
            "limit": prepared_limit(character),
            "filter_schools": sorted({o.school for o in options}),
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/characters/{character_id}/sheet/prepared/edit", response_class=HTMLResponse)
def edit_prepared(request: Request, db: DbSession, character: OwnedCharacter):
    prepared = prepared_spell_ids(db, character)
    selected = [e.spell.slug for e in spellbook(db, character.id) if e.spell_id in prepared]
    return _render_prepared_editor(request, db, character, selected)


@router.post("/characters/{character_id}/sheet/prepared", response_class=HTMLResponse)
def save_prepared(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    picks: Annotated[list[str], Form()] = [],
):
    picks = list(dict.fromkeys(picks))
    book = {entry.spell.slug: entry.spell_id for entry in spellbook(db, character.id)}
    limit = prepared_limit(character)

    error = None
    if limit is None:
        error = "This character doesn't prepare spells."
    elif any(slug not in book for slug in picks):
        error = "You can only prepare spells in your spellbook."
    elif len(picks) > limit:
        error = f"You can prepare at most {limit}. You picked {len(picks)}."
    if error:
        return _render_prepared_editor(request, db, character, picks, error, status_code=400)

    db.execute(
        delete(CharacterPreparedSpell).where(CharacterPreparedSpell.character_id == character.id)
    )
    db.add_all(
        CharacterPreparedSpell(character_id=character.id, spell_id=book[slug]) for slug in picks
    )
    db.commit()
    return refresh_sheet(request, db, user, character)

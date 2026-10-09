from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import delete

from app.auth.dependencies import CurrentUser
from app.auth.models import User
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.core.db import DbSession
from app.core.templates import morph_in_place, templates
from app.features.kinds import KINDS
from app.leveling.service import constitution_modifier
from app.sheet.models import CharacterHpEffect, CharacterPreparedSpell
from app.sheet.rests import (
    damage_reactions,
    feature_uses,
    finish_short_rest,
    hit_dice,
    long_rest,
    recovery_budget,
    set_uses_remaining,
    spend_hit_die,
)
from app.sheet.rules import heal, hit_die_healing, set_temp_hp, take_damage
from app.sheet.service import (
    ability_modifier,
    castable_spells,
    hp_view,
    max_hp,
    play_state,
    prepared_limit,
    prepared_spell_ids,
    set_slots_remaining,
    spell_slots,
    track_max_change,
)
from app.spells.queries import spellbook

router = APIRouter(tags=["sheet"])

SHEET_SELECTOR = "#sheet-page"


def render_sheet(
    request,
    db,
    user: User,
    character: Character,
    errors=None,
    status_code=200,
    resting=False,
    pending_damage: int | None = None,
):
    """The sheet. `resting` shows the Short rest panel, which holds every short-rest action
    (hit dice, Arcane Recovery) so they stay off the main sheet."""
    uses = feature_uses(db, character)
    context = {
        "user": user,
        "character": character,
        "hp": hp_view(db, character),
        # Rest-only features (like Arcane Recovery) appear only in the Short rest panel.
        "resources": [u for u in uses if not u.rest_only],
        "castable": castable_spells(db, character),
        "slots": spell_slots(db, character),
        "prepared_count": len(prepared_spell_ids(db, character)),
        "prepared_limit": prepared_limit(character),
        "has_spellbook": bool(spellbook(db, character.id)),
        "resting": resting,
        "errors": errors or {},
        "pending_damage": pending_damage,
    }
    if pending_damage is not None:
        # Damage is waiting on "use a reaction or take it all"; each reduce reaction shows the
        # ability modifier it adds to its roll.
        context["reactions"] = [
            (r, ability_modifier(db, character, r.option.damage_reaction.get("ability", "")))
            for r in damage_reactions(db, character)
        ]
    if resting:
        context["hit_dice"] = hit_dice(db, character)
        context["recoveries"] = [
            (u, recovery_budget(u)) for u in uses if u.feature.slot_recovery is not None
        ]
    return templates.TemplateResponse(request, "sheet/sheet.html", context, status_code=status_code)


def refresh_sheet(
    request,
    db,
    user,
    character,
    errors=None,
    status_code=200,
    resting=False,
    pending_damage=None,
):
    """Re-render the sheet and morph it into place (see app/core/templates.py)."""
    db.expire_all()  # sessions don't expire on commit; reload what just changed
    response = render_sheet(
        request, db, user, character, errors, status_code, resting, pending_damage
    )
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
    skip_reactions: Annotated[str, Form()] = "",
):
    maximum = max_hp(db, character)
    value = _amount(amount, 0, 999)
    if maximum is None or action not in ("damage", "heal") or value is None:
        errors = {"hp": "Enter a whole number from 0 to 999."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)
    if action == "damage" and value and not skip_reactions and damage_reactions(db, character):
        # Offer reactions like Stone's Endurance before the damage lands.
        return refresh_sheet(request, db, user, character, pending_damage=value)
    state = play_state(db, character)
    (take_damage if action == "damage" else heal)(state, value, maximum)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post("/characters/{character_id}/sheet/hp/react", response_class=HTMLResponse)
def react_to_damage(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    amount: Annotated[str, Form()] = "",
    option_id: Annotated[str, Form()] = "",
    roll: Annotated[str, Form()] = "",
):
    """Use a damage reaction (Stone's Endurance, Storm's Thunder...), then take the damage."""
    maximum = max_hp(db, character)
    value = _amount(amount, 1, 999)
    reaction = next(
        (r for r in damage_reactions(db, character) if str(r.option.id) == option_id), None
    )
    if maximum is None or value is None or reaction is None:
        errors = {"hp": "That reaction isn't available right now."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)

    if reaction.kind == "reduce":
        low, high = reaction.die_count, reaction.die_count * reaction.die_sides
        rolled = _amount(roll, low, high)
        if rolled is None:
            errors = {"reaction": f"Enter your {reaction.dice} roll, from {low} to {high}."}
            return refresh_sheet(
                request, db, user, character, errors, status_code=400, pending_damage=value
            )
        ability = reaction.option.damage_reaction.get("ability")
        reduction = rolled + (ability_modifier(db, character, ability) if ability else 0)
        value = max(0, value - reduction)

    set_uses_remaining(db, character, reaction.uses, reaction.uses.remaining - 1)
    take_damage(play_state(db, character), value, maximum)
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


# --- Spell slots ----------------------------------------------------------------------------


@router.post("/characters/{character_id}/sheet/slots/{level}", response_class=HTMLResponse)
def set_slots(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    level: int,
    remaining: Annotated[str, Form()] = "",
):
    slot = spell_slots(db, character).get(level)
    value = _amount(remaining, 0, slot.maximum) if slot else None
    if value is None:
        errors = {"slots": "That isn't a valid number of slots."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)
    set_slots_remaining(db, character, level, value)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post("/characters/{character_id}/sheet/cast", response_class=HTMLResponse)
def cast_spell(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    spell: Annotated[str, Form()] = "",
    slot_level: Annotated[str, Form()] = "",
):
    """Spend a slot to cast a prepared spell, at its level or higher."""
    # A prepared ritual is listed twice (as a ritual and at its level); casting uses the slot row.
    row = next(
        (r for r in castable_spells(db, character) if r.spell.slug == spell and r.uses_slots), None
    )
    slots = spell_slots(db, character)
    level = _amount(slot_level, 1, 9)

    error = None
    if row is None or not row.uses_slots:
        error = "Only prepared spells of level 1 or higher are cast with a slot."
    elif level is None or level < row.spell.level:
        error = f"{row.spell.name} needs a slot of level {row.spell.level} or higher."
    elif level not in slots or slots[level].remaining == 0:
        error = f"You have no level {level} slots left."
    if error:
        return refresh_sheet(request, db, user, character, {"cast": error}, status_code=400)

    set_slots_remaining(db, character, level, slots[level].remaining - 1)
    db.commit()
    return refresh_sheet(request, db, user, character)


# --- Limited-use features -----------------------------------------------------------------


@router.post("/characters/{character_id}/sheet/uses/{feature_id}", response_class=HTMLResponse)
def set_uses(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    feature_id: int,
    remaining: Annotated[str, Form()] = "",
):
    uses = next((u for u in feature_uses(db, character) if u.feature.id == feature_id), None)
    if uses is None or uses.rest_only:
        raise HTTPException(status_code=404)
    value = _amount(remaining, 0, uses.maximum)
    if value is None:
        errors = {"uses": "That isn't a valid number of uses."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)
    set_uses_remaining(db, character, uses, value)
    db.commit()
    return refresh_sheet(request, db, user, character)


# --- Rests --------------------------------------------------------------------------------


@router.get("/characters/{character_id}/sheet/short-rest", response_class=HTMLResponse)
def open_short_rest(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    return refresh_sheet(request, db, user, character, resting=True)


@router.post("/characters/{character_id}/sheet/short-rest/hit-die", response_class=HTMLResponse)
def short_rest_hit_die(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    class_id: Annotated[str, Form()] = "",
    roll: Annotated[str, Form()] = "",
):
    dice = next((d for d in hit_dice(db, character) if str(d.character_class.id) == class_id), None)
    maximum = max_hp(db, character)
    con_mod = constitution_modifier(db, character)

    error = None
    if dice is None or maximum is None or con_mod is None:
        error = "Set ability scores first: hit dice heal using Constitution."
    elif dice.available == 0:
        error = "You have no hit dice left. They come back on a long rest."
    elif _amount(roll, 1, dice.die) is None:
        error = f"Enter your d{dice.die} roll, from 1 to {dice.die}."
    if error:
        return refresh_sheet(
            request, db, user, character, {"hit_die": error}, status_code=400, resting=True
        )

    spend_hit_die(db, character, dice.character_class.id)
    heal(play_state(db, character), hit_die_healing(int(roll), con_mod), maximum)
    db.commit()
    return refresh_sheet(request, db, user, character, resting=True)


class RecoveryForm(BaseModel):
    """How many slots of each level to recover; blank means none."""

    level_1: str = ""
    level_2: str = ""
    level_3: str = ""
    level_4: str = ""
    level_5: str = ""
    level_6: str = ""
    level_7: str = ""
    level_8: str = ""
    level_9: str = ""


@router.post(
    "/characters/{character_id}/sheet/short-rest/recover/{feature_id}", response_class=HTMLResponse
)
def short_rest_recover(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    feature_id: int,
    form: Annotated[RecoveryForm, Form()],
):
    """Recover expended spell slots with a feature like Arcane Recovery."""
    uses = next((u for u in feature_uses(db, character) if u.feature.id == feature_id), None)
    if uses is None or uses.feature.slot_recovery is None:
        raise HTTPException(status_code=404)
    slots = spell_slots(db, character)
    budget = recovery_budget(uses)
    max_level = uses.feature.slot_recovery["max_slot_level"]

    counts, error = {}, None
    for level, slot in slots.items():
        raw = getattr(form, f"level_{level}").strip() or "0"
        count = _amount(raw, 0, 99)
        if count is None:
            error = "Enter how many slots of each level to recover."
            break
        if count:
            counts[level] = count
            if level > max_level:
                error = f"{uses.feature.name} can't recover slots above level {max_level}."
            elif count > slot.maximum - slot.remaining:
                error = f"You only have {slot.maximum - slot.remaining} level {level} slots spent."
    if error is None:
        if uses.remaining == 0:
            error = f"{uses.feature.name} is used. It comes back on a long rest."
        elif not counts:
            error = "Choose at least one slot to recover."
        elif sum(level * n for level, n in counts.items()) > budget:
            error = f"{uses.feature.name} recovers at most {budget} total slot levels."
    if error:
        return refresh_sheet(
            request, db, user, character, {"recovery": error}, status_code=400, resting=True
        )

    for level, n in counts.items():
        set_slots_remaining(db, character, level, slots[level].remaining + n)
    set_uses_remaining(db, character, uses, uses.remaining - 1)
    db.commit()
    return refresh_sheet(request, db, user, character, resting=True)


@router.post("/characters/{character_id}/sheet/short-rest/finish", response_class=HTMLResponse)
def short_rest_finish(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter
):
    finish_short_rest(db, character)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post("/characters/{character_id}/sheet/long-rest", response_class=HTMLResponse)
def take_long_rest(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    long_rest(db, character)
    db.commit()
    return refresh_sheet(request, db, user, character)

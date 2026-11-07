from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.abilities.queries import constitution_modifier
from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.core.db import DbSession
from app.core.forms import parse_amount
from app.features.dependencies import InPlayChoice
from app.sheet import page, service
from app.sheet.dependencies import CopyableSpell, OwnedAcEffect, OwnedHpEffect
from app.sheet.form import AcEffectForm
from app.sheet.queries import (
    CopyPanel,
    copy_confirmation,
    copy_search,
    feature_uses,
    hit_dice,
    max_hp,
    prepared_editor_view,
    recovery_budget,
    refreshed_prepared_editor_view,
    refreshed_sheet_view,
    sheet_view,
    spell_slots,
)
from app.sheet.rests import finish_short_rest, long_rest, spend_hit_die
from app.sheet.rules import heal, hit_die_healing

router = APIRouter(tags=["sheet"])


@router.get("/characters/{character_id}/sheet", response_class=HTMLResponse)
def show_sheet(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    return page.sheet(request, sheet_view(db, user, character))


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
    outcome = service.change_hp(db, character, action, amount, skip_reactions)
    view = refreshed_sheet_view(db, user, character, pending_damage=outcome.pending_damage)
    return page.refresh_sheet(request, view, outcome.errors)


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
    outcome = service.react_to_damage(db, character, amount, option_id, roll)
    view = refreshed_sheet_view(db, user, character, pending_damage=outcome.pending_damage)
    return page.refresh_sheet(request, view, outcome.errors)


@router.post("/characters/{character_id}/sheet/temp-hp", response_class=HTMLResponse)
def change_temp_hp(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    amount: Annotated[str, Form()] = "",
    source: Annotated[str, Form()] = "",
):
    error = service.change_temp_hp(db, character, amount, source)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"temp_hp": error} if error else None)


@router.post("/characters/{character_id}/sheet/hp-effects", response_class=HTMLResponse)
def add_hp_effect(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    label: Annotated[str, Form()] = "",
    delta: Annotated[str, Form()] = "",
):
    error = service.add_hp_effect(db, character, label, delta)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"effect": error} if error else None)


@router.post(
    "/characters/{character_id}/sheet/hp-effects/{effect_id}/end", response_class=HTMLResponse
)
def end_hp_effect(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    effect: OwnedHpEffect,
):
    service.end_hp_effect(db, character, effect)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


# --- Armor Class effects ------------------------------------------------------------------


@router.post("/characters/{character_id}/sheet/ac-effects/cast", response_class=HTMLResponse)
def cast_ac_spell(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    spell: Annotated[str, Form()] = "",
    slot_level: Annotated[str, Form()] = "",
):
    error = service.cast_ac_spell(db, character, spell, slot_level)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"ac_effect": error} if error else None)


@router.post("/characters/{character_id}/sheet/ac-effects", response_class=HTMLResponse)
def add_ac_effect(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    form: Annotated[AcEffectForm, Form()],
):
    error = service.add_ac_effect(db, character, form)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"ac_effect": error} if error else None)


@router.post(
    "/characters/{character_id}/sheet/ac-effects/{effect_id}/end", response_class=HTMLResponse
)
def end_ac_effect(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    effect: OwnedAcEffect,
):
    service.end_ac_effect(db, effect)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


# --- Prepared spells ----------------------------------------------------------------------


@router.get("/characters/{character_id}/sheet/prepared/edit", response_class=HTMLResponse)
def edit_prepared(request: Request, db: DbSession, character: OwnedCharacter):
    return page.prepared_editor(request, prepared_editor_view(db, character))


@router.post("/characters/{character_id}/sheet/prepared", response_class=HTMLResponse)
def save_prepared(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    picks: Annotated[list[str], Form()] = [],
):
    if error := service.save_prepared(db, character, picks):
        return page.prepared_editor(request, prepared_editor_view(db, character, picks), error)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


@router.post("/characters/{character_id}/sheet/prepared/edit", response_class=HTMLResponse)
def ask_remove(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    picks: Annotated[list[str], Form()] = [],
    asking: Annotated[str, Form()] = "",
):
    """Show (or with no `asking`, hide) "Remove X from your spellbook?" in the editor, keeping
    the unsaved picks."""
    return page.prepared_editor(request, prepared_editor_view(db, character, picks, asking))


@router.post("/characters/{character_id}/sheet/spellbook/remove", response_class=HTMLResponse)
def remove_copied_spell(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    picks: Annotated[list[str], Form()] = [],
    remove: Annotated[str, Form()] = "",
):
    if error := service.remove_copied_spell(db, character, remove):
        return page.prepared_editor(request, prepared_editor_view(db, character, picks), error)
    return page.prepared_editor(request, refreshed_prepared_editor_view(db, character, picks))


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
    error = service.change_slots(db, character, level, remaining)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"slots": error} if error else None)


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
    error = service.spend_slot(db, character, spell, slot_level)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"cast": error} if error else None)


@router.post("/characters/{character_id}/sheet/cast-free", response_class=HTMLResponse)
def cast_free(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    spell: Annotated[str, Form()] = "",
    feature: Annotated[str, Form()] = "",
):
    error = service.cast_free(db, character, spell, feature)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"cast": error} if error else None)


# --- Choices made in play -----------------------------------------------------------------


@router.post("/characters/{character_id}/sheet/choices/{choice_id}", response_class=HTMLResponse)
def set_play_choice(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    choice: InPlayChoice,
    pick: Annotated[str, Form()] = "",
):
    """Pick (or with no `pick`, clear) an in-play choice, like the Transmuter's Stone benefit."""
    error = service.set_play_choice(db, character, choice, pick)
    view = refreshed_sheet_view(db, user, character)
    return page.refresh_sheet(request, view, {"play_choice": error} if error else None)


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
    value = parse_amount(remaining, 0, uses.maximum)
    if value is None:
        errors = {"uses": "That isn't a valid number of uses."}
        return page.refresh_sheet(request, refreshed_sheet_view(db, user, character), errors)
    service.set_uses_remaining(db, character, uses, value)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


@router.post(
    "/characters/{character_id}/sheet/features/{feature_id}/use", response_class=HTMLResponse
)
def use_feature(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, feature_id: int
):
    """Use something that spends another feature's uses, like a magic item's Stonecunning
    spending its charges."""
    uses, feature = next(
        ((u, f) for u in feature_uses(db, character) for f in u.spenders if f.id == feature_id),
        (None, None),
    )
    if uses is None:
        raise HTTPException(status_code=404)
    if uses.remaining < feature.spends_amount:
        error = f"{feature.name} takes {feature.spends_amount}; {uses.remaining} left."
        return page.refresh_sheet(
            request, refreshed_sheet_view(db, user, character), {"uses": error}
        )
    service.set_uses_remaining(db, character, uses, uses.remaining - feature.spends_amount)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


# --- Rests --------------------------------------------------------------------------------


@router.get("/characters/{character_id}/sheet/short-rest", response_class=HTMLResponse)
def open_short_rest(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character, resting=True))


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
    elif parse_amount(roll, 1, dice.die) is None:
        error = f"Enter your d{dice.die} roll, from 1 to {dice.die}."
    if error:
        return page.refresh_sheet(
            request, refreshed_sheet_view(db, user, character, resting=True), {"hit_die": error}
        )

    spend_hit_die(db, character, dice.character_class.id)
    heal(service.play_state(db, character), hit_die_healing(int(roll), con_mod), maximum)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character, resting=True))


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
        count = parse_amount(raw, 0, 99)
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
        return page.refresh_sheet(
            request, refreshed_sheet_view(db, user, character, resting=True), {"recovery": error}
        )

    for level, n in counts.items():
        service.set_slots_remaining(db, character, level, slots[level].remaining + n)
    service.set_uses_remaining(db, character, uses, uses.remaining - 1)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character, resting=True))


@router.post("/characters/{character_id}/sheet/short-rest/finish", response_class=HTMLResponse)
def short_rest_finish(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter
):
    finish_short_rest(db, character)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


@router.post("/characters/{character_id}/sheet/long-rest", response_class=HTMLResponse)
def take_long_rest(request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter):
    long_rest(db, character)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


# --- Copying spells into the spellbook ----------------------------------------------------


@router.get("/characters/{character_id}/sheet/spellbook/copy", response_class=HTMLResponse)
def open_copy_panel(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, q: str = ""
):
    """The copy panel's search step; `q` refills it when coming back from the confirm step."""
    return page.refresh_sheet(
        request, refreshed_sheet_view(db, user, character, copying=CopyPanel(query=q))
    )


@router.get("/characters/{character_id}/sheet/spellbook/copy/search", response_class=HTMLResponse)
def search_copy(request: Request, db: DbSession, character: OwnedCharacter, q: str = ""):
    return page.copy_results(request, character, copy_search(db, character, q))


@router.get("/characters/{character_id}/sheet/spellbook/copy/confirm", response_class=HTMLResponse)
def confirm_copy(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    spell: CopyableSpell,
    q: str = "",
):
    return page.copy_confirm(request, character, copy_confirmation(db, character, spell, q))


@router.post("/characters/{character_id}/sheet/spellbook/copy", response_class=HTMLResponse)
def copy_spell(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    spell: Annotated[str, Form()] = "",
    note: Annotated[str, Form()] = "",
    q: Annotated[str, Form()] = "",
):
    if error := service.copy_spell(db, character, spell, note):
        view = refreshed_sheet_view(db, user, character, copying=CopyPanel(query=q))
        return page.refresh_sheet(request, view, {"copy_spell": error})
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))

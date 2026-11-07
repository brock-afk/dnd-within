from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.abilities.queries import constitution_modifier
from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.content.queries import available
from app.core.db import DbSession, reload_all
from app.core.forms import parse_amount
from app.core.templates import templates
from app.features.kinds import KINDS
from app.features.queries import (
    always_prepared_error,
    always_prepared_reasons,
    applicable_choice,
)
from app.sheet import page, service
from app.sheet.dependencies import OwnedAcEffect, OwnedHpEffect
from app.sheet.form import AcEffectForm
from app.sheet.models import CharacterPreparedSpell
from app.sheet.queries import (
    CopyPanel,
    copy_confirmation,
    copy_search,
    feature_uses,
    granted_spells,
    hit_dice,
    max_hp,
    prepared_limit,
    prepared_spell_ids,
    recovery_budget,
    refreshed_sheet_view,
    sheet_view,
    spell_slots,
    spell_warnings,
    spellbook_notes,
)
from app.sheet.rests import finish_short_rest, long_rest, spend_hit_die
from app.sheet.rules import heal, hit_die_healing
from app.spells.models import Spell, SpellbookEntry
from app.spells.queries import spellbook

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


def _render_prepared_editor(
    request, db, character, selected, error=None, status_code=200, asking=""
):
    """The prepared editor. `asking` is the copied spell whose "Remove from your spellbook?"
    question is showing."""
    warnings = spell_warnings(db, character)
    notes = spellbook_notes(db, character)
    options = [
        replace(
            KINDS["spell"].view(entry.spell),
            warnings=tuple(warnings.get(entry.spell_id, [])),
            note=notes.get(entry.spell_id, ""),
            # Only copied spells: level-up and feature spells change through their choice.
            removable=entry.acquired_via == "copied",
        )
        for entry in spellbook(db, character.id)
    ]
    return templates.TemplateResponse(
        request,
        "sheet/partials/prepared_editor.html",
        {
            "character": character,
            "options": options,
            "selected": selected,
            "known": always_prepared_reasons(db, character),
            "limit": prepared_limit(character),
            "filter_schools": sorted({o.school for o in options}),
            "error": error,
            "asking": asking,
        },
        status_code=status_code,
    )


@router.get("/characters/{character_id}/sheet/prepared/edit", response_class=HTMLResponse)
def edit_prepared(request: Request, db: DbSession, character: OwnedCharacter):
    prepared = prepared_spell_ids(db, character)
    selected = [str(e.spell_id) for e in spellbook(db, character.id) if e.spell_id in prepared]
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
    book = {str(entry.spell_id): entry.spell_id for entry in spellbook(db, character.id)}
    limit = prepared_limit(character)

    error = None
    if limit is None:
        error = "This character doesn't prepare spells."
    elif any(key not in book for key in picks):
        error = "You can only prepare spells in your spellbook."
    elif refused := always_prepared_error(db, character, picks):
        error = refused
    elif len(picks) > limit:
        error = f"You can prepare at most {limit}. You picked {len(picks)}."
    if error:
        return _render_prepared_editor(request, db, character, picks, error, status_code=400)

    db.execute(
        delete(CharacterPreparedSpell).where(CharacterPreparedSpell.character_id == character.id)
    )
    db.add_all(
        CharacterPreparedSpell(character_id=character.id, spell_id=book[key]) for key in picks
    )
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
    return _render_prepared_editor(request, db, character, picks, asking=asking)


@router.post("/characters/{character_id}/sheet/spellbook/remove", response_class=HTMLResponse)
def remove_copied_spell(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    picks: Annotated[list[str], Form()] = [],
    remove: Annotated[str, Form()] = "",
):
    """Remove a copied spell from the spellbook (added by mistake). Preparing it is undone by
    the database (character_prepared_spells cascades from spellbook_entries)."""
    entry = next((e for e in spellbook(db, character.id) if str(e.spell_id) == remove), None)
    if entry is None or entry.acquired_via != "copied":
        error = "Only copied spells can be removed here. Change level-up spells on the Build page."
        return _render_prepared_editor(request, db, character, picks, error, status_code=400)
    db.delete(entry)
    reload_all(db)
    return _render_prepared_editor(request, db, character, [p for p in picks if p != remove])


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
    value = parse_amount(remaining, 0, slot.maximum) if slot else None
    if value is None:
        errors = {"slots": "That isn't a valid number of slots."}
        return page.refresh_sheet(request, refreshed_sheet_view(db, user, character), errors)
    service.set_slots_remaining(db, character, level, value)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


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
    if error:
        return page.refresh_sheet(
            request, refreshed_sheet_view(db, user, character), {"cast": error}
        )
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


@router.post("/characters/{character_id}/sheet/cast-free", response_class=HTMLResponse)
def cast_free(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    spell: Annotated[str, Form()] = "",
    feature: Annotated[str, Form()] = "",
):
    """Cast a spell a feature grants without a slot (Wondrous Alteration's Alter Self),
    spending one use of that feature."""
    granted = granted_spells(db, character).get(int(spell)) if spell.isdigit() else None
    uses = next((u for u in feature_uses(db, character) if str(u.feature.id) == feature), None)
    error = None
    if granted is None or not granted[0].free_cast or uses is None or uses.feature != granted[1]:
        error = "That spell can't be cast for free."
    elif uses.remaining < granted[0].charge_cost:
        error = (
            f"{uses.feature.name}: {uses.remaining} left, and this takes {granted[0].charge_cost}."
            if uses.remaining
            else f"{uses.feature.name}'s free cast is used. It comes back on a long rest."
        )
    if error:
        return page.refresh_sheet(
            request, refreshed_sheet_view(db, user, character), {"cast": error}
        )
    service.set_uses_remaining(db, character, uses, uses.remaining - granted[0].charge_cost)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


# --- Choices made in play -----------------------------------------------------------------


@router.post("/characters/{character_id}/sheet/choices/{choice_id}", response_class=HTMLResponse)
def set_play_choice(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    choice_id: int,
    pick: Annotated[str, Form()] = "",
):
    """Pick (or with no `pick`, clear) an in-play choice, like the Transmuter's Stone benefit."""
    choice = applicable_choice(db, character, choice_id)
    if choice is None or not choice.in_play:
        raise HTTPException(status_code=404)
    kind = KINDS[choice.kind]
    if pick:
        error = kind.save(db, choice, character.id, [pick])
        if error:
            errors = {"play_choice": error}
            return page.refresh_sheet(request, refreshed_sheet_view(db, user, character), errors)
    else:
        kind.clear(db, [choice.id], character.id)
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))


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


def _copyable(db, key: str) -> Spell | None:
    if not key.isdigit():
        return None
    found = db.scalar(select(Spell).where(Spell.id == int(key), available(Spell)))
    return found if found is not None and found.level >= 1 else None


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
    """Spells matching the typed name, swapped into the panel's result list."""
    return templates.TemplateResponse(
        request,
        "sheet/partials/copy_results.html",
        {"character": character, "copy": copy_search(db, character, q)},
    )


@router.get("/characters/{character_id}/sheet/spellbook/copy/confirm", response_class=HTMLResponse)
def confirm_copy(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    spell: str = "",
    q: str = "",
):
    """The confirm step for one spell: its cost, rule markers and an optional note."""
    found = _copyable(db, spell)
    if found is None:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request,
        "sheet/partials/copy_confirm.html",
        {
            "character": character,
            "errors": {},
            "copy_confirm": copy_confirmation(db, character, found, q),
        },
    )


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
    """Copy a spell into the spellbook from a scroll or another book. Any spell is allowed
    (rule-breaking ones get a marker); the gold and time are the player's to track."""
    found = _copyable(db, spell)
    in_book = {entry.spell_id for entry in spellbook(db, character.id)}
    error = None
    if found is None:
        error = "Choose a spell of level 1 or higher to copy."
    elif found.id in in_book:
        error = f"{found.name} is already in your spellbook."
    else:
        error = always_prepared_error(db, character, [str(found.id)])
    if error:
        panel = CopyPanel(query=q)
        return page.refresh_sheet(
            request, refreshed_sheet_view(db, user, character, copying=panel), {"copy_spell": error}
        )
    db.add(
        SpellbookEntry(
            character_id=character.id,
            spell_id=found.id,
            acquired_via="copied",
            source_note=note.strip()[:120] or None,
        )
    )
    return page.refresh_sheet(request, refreshed_sheet_view(db, user, character))

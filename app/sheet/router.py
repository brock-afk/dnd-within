import re
from dataclasses import dataclass, replace
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.auth.dependencies import CurrentUser
from app.auth.models import User
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.content.queries import available
from app.core.db import DbSession
from app.core.templates import morph_in_place, templates
from app.features.kinds import KINDS
from app.features.service import applicable_choice, play_choices
from app.inventory.service import (
    COINS,
    MAX_ATTUNED,
    ac_scrolls,
    coin_summary,
    coin_values,
    healing_uses,
    inventory,
    item_features,
)
from app.sharing.service import public_share
from app.inventory.service import digest as inventory_digest
from app.leveling.service import constitution_modifier
from app.sheet.models import CharacterAcEffect, CharacterHpEffect, CharacterPreparedSpell
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
    active_ac_spell_ids,
    COPY_SEARCH_MIN,
    ability_modifier,
    ability_rows,
    attributes,
    granted_spells,
    ac_spells,
    apply_ac_spell,
    armor_class,
    castable_spells,
    copy_warnings,
    hp_view,
    max_hp,
    play_state,
    prepared_limit,
    prepared_spell_ids,
    search_copyable,
    set_slots_remaining,
    skill_rows,
    spell_slots,
    spell_warnings,
    spellbook_notes,
    track_max_change,
)
from app.spells.models import Spell, SpellbookEntry
from app.spells.queries import spellbook

router = APIRouter(tags=["sheet"])

SHEET_SELECTOR = "#sheet-page"
ACTION_LABELS = {"action": "Action", "bonus_action": "Bonus Action", "reaction": "Reaction"}


def render_sheet(
    request,
    db,
    user: User,
    character: Character,
    errors=None,
    status_code=200,
    resting=False,
    pending_damage: int | None = None,
    copying: "CopyPanel | None" = None,
    notices=None,
    read_only: bool = False,
    base_url: str | None = None,
):
    """The sheet. `resting` shows the Short rest panel, which holds every short-rest action
    (hit dice, Arcane Recovery) so they stay off the main sheet. `notices` report what just
    happened (a potion's roll). `read_only` is the shared view: the same sheet with every
    control left out, linking within `base_url` (/shared/<token>) instead of the owner's."""
    uses = feature_uses(db, character)
    attrs = attributes(db, character)
    items = inventory(db, character)
    context = {
        "user": user,
        "character": character,
        "hp": hp_view(db, character),
        "abilities": ability_rows(db, character, attrs),
        "attributes": attrs,
        "skills": skill_rows(db, character),
        "ac": armor_class(db, character),
        "ac_spells": ac_spells(db, character),
        # Rest-only features (like Arcane Recovery) appear only in the Short rest panel.
        "resources": [u for u in uses if not u.rest_only],
        "free_uses": {u.feature.id: u for u in uses},
        "play_choices": play_choices(db, character),
        "castable": castable_spells(db, character),
        "slots": spell_slots(db, character),
        "prepared_count": len(prepared_spell_ids(db, character)),
        "prepared_limit": prepared_limit(character),
        "has_spellbook": bool(spellbook(db, character.id)),
        "resting": resting,
        "action_labels": ACTION_LABELS,
        "items": items,
        "item_features": item_features(db, items),
        "coin_summary": coin_summary(coin_values(db, character)),
        "coin_labels": COINS,
        "inventory_digest": inventory_digest(db, character, items),
        "max_attuned": MAX_ATTUNED,
        "healing_uses": healing_uses(items),
        "ac_scrolls": ac_scrolls(items, active_ac_spell_ids(db, character)),
        "notices": notices or {},
        "read_only": read_only,
        "base_url": base_url or f"/characters/{character.id}",
        "share": None if read_only else public_share(db, character),
        "errors": errors or {},
        "pending_damage": pending_damage,
        "spell_warnings": spell_warnings(db, character),
        "spell_notes": spellbook_notes(db, character),
        "copying": copying,
    }
    if copying:
        context.update(_copy_context(db, character, copying))
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
    copying=None,
    notices=None,
):
    """Re-render the sheet and morph it into place (see app/core/templates.py)."""
    db.expire_all()  # sessions don't expire on commit; reload what just changed
    response = render_sheet(
        request, db, user, character, errors, status_code, resting, pending_damage, copying,
        notices,
    )
    return morph_in_place(response, SHEET_SELECTOR)


def _amount(raw: str, low: int, high: int) -> int | None:
    """A whole number in [low, high]. Accepts a leading "+", and "−" (the minus sign shown in
    placeholders) as well as "-"."""
    raw = raw.strip().replace("−", "-")
    if re.fullmatch(r"[+-]?\d{1,4}", raw) and low <= int(raw) <= high:
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
    """Cast a prepared AC spell on yourself (Mage Armor, Barkskin): spend the slot and
    apply its effect. Casting from the spell list doesn't, since the target may be someone else."""
    if spell not in {str(a.spell.id) for a in ac_spells(db, character)}:
        found, error = None, "Only prepared spells that change your AC can be cast here."
    else:
        found, error = _spend_slot(db, character, spell, slot_level)
    if error:
        return refresh_sheet(request, db, user, character, {"ac_effect": error}, status_code=400)
    apply_ac_spell(db, character, found)
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post("/characters/{character_id}/sheet/ac-effects", response_class=HTMLResponse)
def add_ac_effect(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    label: Annotated[str, Form()] = "",
    kind: Annotated[str, Form()] = "",
    value: Annotated[str, Form()] = "",
):
    """By hand: Mage Armor base 13 (+ DEX), Shield of Faith bonus +2, Barkskin minimum 17."""
    label = label.strip()[:80]
    if kind == "base":
        amount = _amount(value, 10, 30)
        problem = "a base AC from 10 to 30 (e.g. Mage Armor, 13)"
    elif kind == "minimum":
        amount = _amount(value, 10, 30)
        problem = "a minimum AC from 10 to 30 (e.g. Barkskin, 17)"
    else:
        kind = "bonus"
        amount = _amount(value, -20, 20)
        problem = "a non-zero bonus (e.g. Shield of Faith, +2)"
    if not label or not amount:
        errors = {"ac_effect": f"Give the effect a name and {problem}."}
        return refresh_sheet(request, db, user, character, errors, status_code=400)
    db.add(CharacterAcEffect(character_id=character.id, label=label, kind=kind, value=amount))
    db.commit()
    return refresh_sheet(request, db, user, character)


@router.post(
    "/characters/{character_id}/sheet/ac-effects/{effect_id}/end", response_class=HTMLResponse
)
def end_ac_effect(
    request: Request, db: DbSession, user: CurrentUser, character: OwnedCharacter, effect_id: int
):
    effect = db.get(CharacterAcEffect, effect_id)
    if effect is None or effect.character_id != character.id:
        raise HTTPException(status_code=404)
    db.delete(effect)
    db.commit()
    return refresh_sheet(request, db, user, character)


# --- Prepared spells ----------------------------------------------------------------------


def _render_prepared_editor(
    request, db, character, selected, error=None, status_code=200, asking=""
):
    """The prepared editor. `asking` is the copied spell whose "Remove from your spellbook?"
    question is showing."""
    warnings = spell_warnings(db, character)
    notes = spellbook_notes(db, character)
    # A granted spell is prepared anyway, so preparing it from the book would waste a pick.
    for spell_id, (feature_spell, feature) in granted_spells(db, character).items():
        if feature_spell.always_prepared:
            notes[spell_id] = f"Always prepared ({feature.name})"
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
    db.commit()
    return refresh_sheet(request, db, user, character)


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
    db.commit()
    db.expire_all()
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
    found, error = _spend_slot(db, character, spell, slot_level)
    if error:
        return refresh_sheet(request, db, user, character, {"cast": error}, status_code=400)
    db.commit()
    return refresh_sheet(request, db, user, character)


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
        return refresh_sheet(request, db, user, character, {"cast": error}, status_code=400)
    set_uses_remaining(db, character, uses, uses.remaining - granted[0].charge_cost)
    db.commit()
    return refresh_sheet(request, db, user, character)


def _spend_slot(db, character, spell_key: str, slot_level: str) -> tuple[Spell | None, str | None]:
    """Spend the slot for casting a prepared spell at `slot_level` (its level or higher).
    Returns (the spell, None), or (None, what's wrong) without spending anything."""
    # A prepared ritual is listed twice (as a ritual and at its level); casting uses the slot row.
    row = next(
        (r for r in castable_spells(db, character) if str(r.spell.id) == spell_key and r.uses_slots),
        None,
    )
    slots = spell_slots(db, character)
    level = _amount(slot_level, 1, 9)
    if row is None:
        return None, "Only prepared spells of level 1 or higher are cast with a slot."
    if level is None or level < row.spell.level:
        return None, f"{row.spell.name} needs a slot of level {row.spell.level} or higher."
    if level not in slots or slots[level].remaining == 0:
        return None, f"You have no level {level} slots left."
    set_slots_remaining(db, character, level, slots[level].remaining - 1)
    return row.spell, None


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
            return refresh_sheet(request, db, user, character, errors, status_code=400)
    else:
        kind.clear(db, [choice.id], character.id)
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


@router.post("/characters/{character_id}/sheet/features/{feature_id}/use", response_class=HTMLResponse)
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
        return refresh_sheet(request, db, user, character, {"uses": error}, status_code=400)
    set_uses_remaining(db, character, uses, uses.remaining - feature.spends_amount)
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


# --- Copying spells into the spellbook ----------------------------------------------------


@dataclass(frozen=True)
class CopyPanel:
    """What the copy panel shows: the search (with `query` typed), or the confirm step for
    `spell`."""

    query: str = ""
    spell: Spell | None = None


def _copy_cost(spell: Spell) -> str:
    """2024 rules: 2 hours and 50 GP per spell level."""
    return f"{2 * spell.level} hours and {50 * spell.level} GP"


def _copy_results(db, character, query: str) -> dict:
    spells = search_copyable(db, query)
    in_book = {entry.spell_id for entry in spellbook(db, character.id)}
    return {
        "query": query.strip(),
        "min_length": COPY_SEARCH_MIN,
        "results": [
            (spell, spell.id in in_book, found)
            for spell, found in copy_warnings(db, character, spells).items()
        ],
    }


def _copy_context(db, character, panel: CopyPanel) -> dict:
    if panel.spell is not None:
        return _confirm_context(db, character, panel.spell, panel.query)
    return {"copy": _copy_results(db, character, panel.query)}


def _confirm_context(db, character, spell: Spell, query: str) -> dict:
    return {
        "copy_confirm": {
            "spell": spell,
            "query": query,
            "cost": _copy_cost(spell),
            "warnings": copy_warnings(db, character, [spell])[spell],
        }
    }


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
    return refresh_sheet(request, db, user, character, copying=CopyPanel(query=q))


@router.get("/characters/{character_id}/sheet/spellbook/copy/search", response_class=HTMLResponse)
def search_copy(request: Request, db: DbSession, character: OwnedCharacter, q: str = ""):
    """Spells matching the typed name, swapped into the panel's result list."""
    return templates.TemplateResponse(
        request,
        "sheet/partials/copy_results.html",
        {"character": character, "copy": _copy_results(db, character, q)},
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
        {"character": character, "errors": {}, **_confirm_context(db, character, found, q)},
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
    if error:
        panel = CopyPanel(query=q, spell=found if found and found.id not in in_book else None)
        return refresh_sheet(
            request, db, user, character, {"copy_spell": error}, status_code=400, copying=panel
        )
    db.add(
        SpellbookEntry(
            character_id=character.id,
            spell_id=found.id,
            acquired_via="copied",
            source_note=note.strip()[:120] or None,
        )
    )
    db.commit()
    return refresh_sheet(request, db, user, character)

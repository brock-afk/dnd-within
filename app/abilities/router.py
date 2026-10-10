from collections import Counter
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.abilities.rules import (
    ABILITIES,
    MAX_SCORE,
    METHODS,
    POINT_BUY_BUDGET,
    POINT_BUY_COSTS,
    STANDARD_ARRAY,
    Ability,
    modifier,
    parse_rolls,
    parse_scores,
    point_buy_spent,
    point_buy_step,
    unassigned,
    validate,
)
from app.abilities.service import ability_views
from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.characters.page import refresh_character_page
from app.core.db import DbSession
from app.core.templates import templates
from app.features.kinds import KINDS, source_name
from app.features.models import Choice
from app.features.service import applicable_choice, remove_inapplicable_picks
from app.sheet.service import max_hp, track_max_change

router = APIRouter(tags=["abilities"])


class AbilityForm(BaseModel):
    method: str = ""
    strength: str = ""
    dexterity: str = ""
    constitution: str = ""
    intelligence: str = ""
    wisdom: str = ""
    charisma: str = ""
    rolls: list[str] = []  # manual entry: the six rolled numbers
    step: str = ""  # point buy: "<column>:1" or "<column>:-1" from a stepper button
    reset: str = ""  # set by the Reset button

    def raw_scores(self) -> dict[str, str]:
        return {a.column: getattr(self, a.column) for a in ABILITIES}


@dataclass
class Option:
    value: int
    disabled: bool  # already given to another ability


@dataclass
class Row:
    ability: Ability
    score: int | None
    error: str | None = None
    options: list[Option] = field(default_factory=list)  # standard array / manual
    can_decrease: bool = False  # point buy
    can_increase: bool = False
    cost: int | None = None  # point buy: total points this score costs

    @property
    def modifier(self) -> str:
        if self.score is None:
            return ""
        mod = modifier(self.score)
        return f"+{mod}" if mod >= 0 else f"−{-mod}"


def _render_editor(
    request: Request,
    character: Character,
    method: str,
    scores: dict[str, int | None],
    rolls: list[int | None],
    errors: dict[str, str] | None = None,
    status_code: int = 200,
):
    errors = errors or {}
    remaining = POINT_BUY_BUDGET - point_buy_spent(scores)
    pool = STANDARD_ARRAY if method == "standard_array" else [r for r in rolls if r is not None]
    rows = []
    for a in ABILITIES:
        score = scores[a.column]
        row = Row(a, score, errors.get(a.column))
        if method == "point_buy":
            if score in POINT_BUY_COSTS:
                row.cost = POINT_BUY_COSTS[score]
                row.can_decrease = score > 8
                row.can_increase = (
                    score < 15 and POINT_BUY_COSTS[score + 1] - row.cost <= remaining
                )
        else:
            # A value is free for this ability if the pool still has a copy of it once the
            # other abilities' picks are taken out. Duplicate rolls count separately.
            others = {c: s for c, s in scores.items() if c != a.column}
            free = Counter(unassigned(pool, others))
            row.options = [Option(v, free[v] == 0) for v in sorted(set(pool), reverse=True)]
        rows.append(row)

    return templates.TemplateResponse(
        request,
        "abilities/partials/ability_form.html",
        {
            "character": character,
            "method": method,
            "methods": METHODS,
            "rows": rows,
            "rolls": rolls,
            "has_pool": bool(pool),
            "left_to_assign": sorted(unassigned(pool, scores), reverse=True),
            "remaining": remaining,
            "budget": POINT_BUY_BUDGET,
            "errors": errors,
        },
        status_code=status_code,
    )


def _saved_state(character: Character, method: str):
    """What a freshly opened tab shows, starting from the saved scores where they fit."""
    saved = {a.column: getattr(character, a.column) for a in ABILITIES}
    has_saved = character.ability_method is not None
    if method == "point_buy":
        fits = has_saved and all(v in POINT_BUY_COSTS for v in saved.values())
        scores = saved if fits and point_buy_spent(saved) <= POINT_BUY_BUDGET else None
        return scores or {a.column: 8 for a in ABILITIES}, []
    if method == "manual" and has_saved:
        # Reopen with the saved scores as the "rolls", already assigned.
        return saved, sorted(saved.values(), reverse=True)
    if method == "standard_array" and character.ability_method == "standard_array":
        return saved, []
    return {a.column: None for a in ABILITIES}, [None] * 6


@router.get("/characters/{character_id}/abilities/edit", response_class=HTMLResponse)
def edit_abilities(request: Request, character: OwnedCharacter, method: str = ""):
    if method not in METHODS:
        method = character.ability_method or "standard_array"
    scores, rolls = _saved_state(character, method)
    return _render_editor(request, character, method, scores, rolls)


@router.post("/characters/{character_id}/abilities/preview", response_class=HTMLResponse)
def preview_abilities(
    request: Request, character: OwnedCharacter, form: Annotated[AbilityForm, Form()]
):
    """Redraw the editor after a stepper click or a changed value: modifiers, costs, and
    which buttons are enabled all come from the server."""
    method = form.method if form.method in METHODS else "standard_array"
    scores = parse_scores(form.raw_scores())
    if form.reset:
        # Back to a fresh tab: point buy starts every score at 8, the others clear the
        # assignments. Manual entry keeps the rolls, since those came from real dice.
        scores = {column: None for column in scores}
    if method == "point_buy":
        scores = {column: score or 8 for column, score in scores.items()}
        column, _, delta = form.step.partition(":")
        if column in scores and delta in ("1", "-1"):
            point_buy_step(scores, column, int(delta))
    return _render_editor(request, character, method, scores, parse_rolls(form.rolls))


@router.post("/characters/{character_id}/abilities")
def save_abilities(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    form: Annotated[AbilityForm, Form()],
):
    scores = parse_scores(form.raw_scores())
    rolls = parse_rolls(form.rolls)
    if errors := validate(form.method, scores, rolls):
        method = form.method if form.method in METHODS else "standard_array"
        return _render_editor(request, character, method, scores, rolls, errors, status_code=400)

    old_max = max_hp(db, character)
    character.ability_method = form.method
    for column, score in scores.items():
        setattr(character, column, score)
    # A Constitution change moves max HP: an increase raises current HP too, a decrease caps it.
    track_max_change(db, character, old_max, heal=True)
    db.commit()
    return refresh_character_page(request, db, user, character)


# --- Ability score increases (a background's +2/+1 or +1/+1/+1) ---------------------------


class IncreaseForm(BaseModel):
    split: str = "uneven"  # "uneven" (+2 and +1) or "even" (+1 to each)
    plus2: str = ""
    plus1: str = ""
    changed: str = ""  # preview: which column was just clicked, "plus2" or "plus1"


@dataclass
class IncreaseRow:
    abbr: str
    name: str
    before: int | None  # with every other bonus; None until ability scores are set
    amount: int

    @property
    def after(self) -> int | None:
        return None if self.before is None else min(self.before + self.amount, MAX_SCORE)

    @property
    def capped(self) -> bool:
        return self.before is not None and self.before + self.amount > MAX_SCORE


def _increase_choice(db: DbSession, character: Character, choice_id: int) -> Choice:
    choice = applicable_choice(db, character, choice_id)
    if choice is None or choice.kind != "ability_scores":
        raise HTTPException(status_code=404)
    return choice


def render_increase_form(
    request: Request,
    db: DbSession,
    character: Character,
    choice: Choice,
    form: IncreaseForm,
    error: str | None = None,
    status_code: int = 200,
):
    """The +2/+1 editor: one row per ability with a +2 and a +1 radio, or just +1 each."""
    even = form.split == "even"
    amounts = KINDS["ability_scores"].split(choice, form.plus2, form.plus1, even) or {}
    if not even:  # show a half-made pick too, e.g. only the +2 chosen so far
        amounts = {form.plus1: 1, form.plus2: 2} | amounts
    before = {a.abbr: a.total for a in ability_views(db, character, choice.id) or []}
    names = {a.abbr: a.name for a in ABILITIES}
    rows = [
        IncreaseRow(abbr, names[abbr], before.get(abbr), amounts.get(abbr, 0))
        for abbr in choice.criteria["from"]
    ]
    return templates.TemplateResponse(
        request,
        "abilities/partials/increase_form.html",
        {
            "character": character,
            "choice": choice,
            "source": source_name(db, choice.feature),
            "even": even,
            "form": form,
            "rows": rows,
            "max_score": MAX_SCORE,
            "error": error,
        },
        status_code=status_code,
    )


def increase_form_for(request: Request, db: DbSession, character: Character, choice: Choice):
    """The editor opened from a Choose or Change button, starting from the saved pick."""
    saved = KINDS["ability_scores"].picked_amounts(db, choice, character.id)
    if saved and set(saved.values()) == {1}:
        form = IncreaseForm(split="even")
    else:
        by_amount = {n: abbr for abbr, n in saved.items()}
        form = IncreaseForm(plus2=by_amount.get(2, ""), plus1=by_amount.get(1, ""))
    return render_increase_form(request, db, character, choice, form)


@router.post(
    "/characters/{character_id}/ability-increases/{choice_id}/preview",
    response_class=HTMLResponse,
)
def preview_increases(
    request: Request,
    db: DbSession,
    character: OwnedCharacter,
    choice_id: int,
    form: Annotated[IncreaseForm, Form()],
):
    choice = _increase_choice(db, character, choice_id)
    # One ability can't take both: the column just clicked wins, the other is cleared.
    if form.plus2 and form.plus2 == form.plus1:
        if form.changed == "plus2":
            form.plus1 = ""
        else:
            form.plus2 = ""
    return render_increase_form(request, db, character, choice, form)


@router.post("/characters/{character_id}/ability-increases/{choice_id}")
def save_increases(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    character: OwnedCharacter,
    choice_id: int,
    form: Annotated[IncreaseForm, Form()],
):
    choice = _increase_choice(db, character, choice_id)
    kind = KINDS["ability_scores"]
    split = kind.split(choice, form.plus2, form.plus1, form.split == "even")
    if split is None:
        error = "Choose where the +2 and the +1 go."
        return render_increase_form(request, db, character, choice, form, error, status_code=400)

    old_max = max_hp(db, character)
    kind.save(db, choice, character.id, [kind.key(split)])
    remove_inapplicable_picks(db, character)
    # A Constitution increase raises max HP, and current HP with it.
    track_max_change(db, character, old_max, heal=True)
    db.commit()
    return refresh_character_page(request, db, user, character)

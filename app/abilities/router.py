from collections import Counter
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.abilities.rules import (
    ABILITIES,
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
from app.auth.dependencies import CurrentUser
from app.characters.dependencies import OwnedCharacter
from app.characters.models import Character
from app.characters.page import refresh_character_page
from app.core.db import DbSession
from app.core.templates import templates

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

    character.ability_method = form.method
    for column, score in scores.items():
        setattr(character, column, score)
    db.commit()
    return refresh_character_page(request, db, user, character)

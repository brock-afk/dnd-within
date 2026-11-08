from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.abilities.form import IncreaseForm
from app.abilities.models import CharacterAbilityBonus
from app.abilities.rules import (
    ABILITIES,
    MAX_SCORE,
    METHODS,
    POINT_BUY_BUDGET,
    POINT_BUY_COSTS,
    STANDARD_ARRAY,
    Ability,
    modifier,
    point_buy_spent,
    unassigned,
)
from app.characters.models import Character
from app.features.kinds import KINDS, source_name
from app.features.models import Choice


def _signed(mod: int) -> str:
    return f"+{mod}" if mod >= 0 else f"−{-mod}"


@dataclass(frozen=True)
class AbilityView:
    abbr: str
    name: str
    base: int
    bonus: int

    @property
    def total(self) -> int:
        return min(self.base + self.bonus, MAX_SCORE)

    @property
    def mod(self) -> int:
        return modifier(self.total)

    @property
    def modifier(self) -> str:
        return _signed(self.mod)


def bonus_totals(
    db: Session, character: Character, except_choice_id: int | None = None
) -> dict[str, int]:
    query = select(CharacterAbilityBonus).where(CharacterAbilityBonus.character_id == character.id)
    if except_choice_id is not None:
        query = query.where(CharacterAbilityBonus.choice_id != except_choice_id)
    bonuses: dict[str, int] = defaultdict(int)
    for row in db.scalars(query):
        bonuses[row.ability] += row.amount
    return bonuses


def ability_views(
    db: Session, character: Character, except_choice_id: int | None = None
) -> list[AbilityView] | None:
    if character.ability_method is None:
        return None
    bonuses = bonus_totals(db, character, except_choice_id)
    return [
        AbilityView(a.abbr, a.name, getattr(character, a.column), bonuses[a.abbr])
        for a in ABILITIES
    ]


def constitution_modifier(db: Session, character: Character) -> int | None:
    abilities = ability_views(db, character)
    if abilities is None:
        return None
    return next(a for a in abilities if a.abbr == "CON").mod


@dataclass(frozen=True)
class Option:
    value: int
    disabled: bool


@dataclass
class Row:
    ability: Ability
    score: int | None
    error: str | None = None
    options: list[Option] = field(default_factory=list)
    can_decrease: bool = False
    can_increase: bool = False
    cost: int | None = None

    @property
    def modifier(self) -> str:
        return "" if self.score is None else _signed(modifier(self.score))


@dataclass(frozen=True)
class AbilityEditorView:
    character: Character
    method: str
    methods: dict[str, str]
    rows: list[Row]
    rolls: list[int | None]
    has_pool: bool
    left_to_assign: list[int]
    remaining: int
    budget: int
    errors: dict[str, str]


def ability_editor_view(
    character: Character,
    method: str,
    scores: dict[str, int | None],
    rolls: list[int | None],
    errors: dict[str, str] | None = None,
) -> AbilityEditorView:
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
                row.can_increase = score < 15 and POINT_BUY_COSTS[score + 1] - row.cost <= remaining
        else:
            others = {c: s for c, s in scores.items() if c != a.column}
            free = Counter(unassigned(pool, others))
            row.options = [Option(v, free[v] == 0) for v in sorted(set(pool), reverse=True)]
        rows.append(row)
    return AbilityEditorView(
        character=character,
        method=method,
        methods=METHODS,
        rows=rows,
        rolls=rolls,
        has_pool=bool(pool),
        left_to_assign=sorted(unassigned(pool, scores), reverse=True),
        remaining=remaining,
        budget=POINT_BUY_BUDGET,
        errors=errors,
    )


def saved_editor_view(character: Character, method: str) -> AbilityEditorView:
    if method not in METHODS:
        method = character.ability_method or "standard_array"
    saved = {a.column: getattr(character, a.column) for a in ABILITIES}
    has_saved = character.ability_method is not None
    if method == "point_buy":
        fits = has_saved and all(v in POINT_BUY_COSTS for v in saved.values())
        fits = fits and point_buy_spent(saved) <= POINT_BUY_BUDGET
        scores, rolls = (saved if fits else dict.fromkeys(saved, 8)), []
    elif method == "manual" and has_saved:
        scores, rolls = saved, sorted(saved.values(), reverse=True)
    elif method == "standard_array" and character.ability_method == "standard_array":
        scores, rolls = saved, []
    else:
        scores, rolls = dict.fromkeys(saved), [None] * 6
    return ability_editor_view(character, method, scores, rolls)


@dataclass(frozen=True)
class IncreaseRow:
    abbr: str
    name: str
    before: int | None
    amount: int

    @property
    def after(self) -> int | None:
        return None if self.before is None else min(self.before + self.amount, MAX_SCORE)

    @property
    def capped(self) -> bool:
        return self.before is not None and self.before + self.amount > MAX_SCORE


@dataclass(frozen=True)
class IncreaseView:
    character: Character
    choice: Choice
    source: str
    even: bool
    form: IncreaseForm
    rows: list[IncreaseRow]
    max_score: int


def increase_view(
    db: Session, character: Character, choice: Choice, form: IncreaseForm
) -> IncreaseView:
    even = form.split == "even"
    amounts = KINDS["ability_scores"].split(choice, form.plus2, form.plus1, even) or {}
    if not even:
        amounts = {form.plus1: 1, form.plus2: 2} | amounts
    before = {a.abbr: a.total for a in ability_views(db, character, choice.id) or []}
    names = {a.abbr: a.name for a in ABILITIES}
    return IncreaseView(
        character=character,
        choice=choice,
        source=source_name(db, choice.feature),
        even=even,
        form=form,
        rows=[
            IncreaseRow(abbr, names[abbr], before.get(abbr), amounts.get(abbr, 0))
            for abbr in choice.criteria["from"]
        ],
        max_score=MAX_SCORE,
    )


def saved_increase_view(db: Session, character: Character, choice: Choice) -> IncreaseView:
    saved = KINDS["ability_scores"].picked_amounts(db, choice, character.id)
    if saved and set(saved.values()) == {1}:
        form = IncreaseForm(split="even")
    else:
        by_amount = {n: abbr for abbr, n in saved.items()}
        form = IncreaseForm(plus2=by_amount.get(2, ""), plus1=by_amount.get(1, ""))
    return increase_view(db, character, choice, form)

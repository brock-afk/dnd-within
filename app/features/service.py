from sqlalchemy import select
from sqlalchemy.orm import Session

from app.characters.models import Character
from app.features.kinds import KINDS, current_count
from app.features.models import Choice
from app.features.queries import (
    always_prepared_error,
    applicable_choice,
    feature_groups,
)
from app.sheet.service import tracking_max_hp


def save_choice(db: Session, character: Character, choice: Choice, picks: list[str]) -> str | None:
    picks = list(dict.fromkeys(picks))
    count = current_count(db, character, choice)
    if len(picks) != count:
        wanted = "one" if count == 1 else f"exactly {count}"
        return f"Choose {wanted}." + (f" You picked {len(picks)}." if picks else "")
    kind = KINDS[choice.kind]
    if kind.blocks_always_prepared and (error := always_prepared_error(db, character, picks)):
        return error
    with tracking_max_hp(db, character, heal=True):
        if error := kind.save(db, choice, character.id, picks):
            return error
        remove_inapplicable_picks(db, character)
    return None


def remove_inapplicable_picks(db: Session, character: Character) -> None:
    while True:
        changed = False
        for source in KINDS.values():
            stale = [
                cid
                for cid in source.picked_choice_ids(db, character.id)
                if not applicable_choice(db, character, cid)
            ]
            if stale:
                source.clear(db, stale, character.id)
                changed = True
        changed |= KINDS["option"].drop_unmet(db, character)
        options = KINDS["option"]
        ids = options.picked_choice_ids(db, character.id)
        growing = db.scalars(
            select(Choice).where(Choice.id.in_(ids), Choice.count_by_level.is_not(None))
        )
        for choice in growing:
            changed |= options.trim(db, choice, character.id, current_count(db, character, choice))
        changed |= KINDS["spell"].drop_above_slots(db, character)
        if not changed:
            break
        db.flush()
    KINDS["expertise"].remove_unproficient(db, character.id)


def fill_fixed_choices(db: Session, character: Character) -> None:
    for group in feature_groups(db, character):
        for fv in group.features:
            for cv in fv.choices:
                if cv.picked or cv.choice.in_play:
                    continue
                kind = KINDS[cv.choice.kind]
                options = kind.options(db, cv.choice, character)
                if len(options) == cv.count:
                    kind.save(db, cv.choice, character.id, [o.key for o in options])

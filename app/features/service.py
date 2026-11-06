"""Saving choices, and keeping a character's picks consistent after a change. Each operation
returns an error message with nothing changed, or None once it's done. They flush, never
commit."""

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
    """Replace the choice's picks. Picks a new pick makes stale go too (switching subclass
    drops the old one's), and current HP follows any max HP change (a Constitution increase)."""
    picks = list(dict.fromkeys(picks))  # drop duplicates, keep order
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
    """Delete picks for choices the character no longer has, e.g. after losing a level or
    switching subclass; options whose prerequisites no longer hold; the newest picks of a
    growing choice beyond its count; and Expertise in skills they're no longer proficient in.

    Repeats until nothing changes, because clearing one pick can make others stale: clearing
    a subclass removes its features, so their picks go too, and unpicking Pact of the Blade
    drops Thirsting Blade. Doesn't commit; the caller does, together with whatever made the
    picks stale.
    """
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
        # Options whose prerequisite (a level, another option) no longer holds, before
        # trimming, so a trim never keeps a pick that's about to go anyway.
        changed |= KINDS["option"].drop_unmet(db, character)
        # A growing choice that shrank (a level lost) drops its last picks in list order:
        # saving replaces a choice's whole set, so which pick is newest isn't known. Only
        # option choices can grow (ChoiceDef).
        options = KINDS["option"]
        ids = options.picked_choice_ids(db, character.id)
        growing = db.scalars(
            select(Choice).where(Choice.id.in_(ids), Choice.count_by_level.is_not(None))
        )
        for choice in growing:
            changed |= options.trim(db, choice, character.id, current_count(db, character, choice))
        # Spells above the slot level their class now reaches (`max_level: class_slots`).
        changed |= KINDS["spell"].drop_above_slots(db, character)
        if not changed:
            break
        db.flush()
    # Expertise needs proficiency, which a changed skill pick may have just removed.
    KINDS["expertise"].remove_unproficient(db, character.id)


def fill_fixed_choices(db: Session, character: Character) -> None:
    """Pick choices that offer exactly as many options as they ask for, like a background's
    Animal Handling. A choice the save rejects (the character already has that skill from
    elsewhere) is left to pick by hand, as the rules say to choose another."""
    for group in feature_groups(db, character):
        for fv in group.features:
            for cv in fv.choices:
                if cv.picked or cv.choice.in_play:
                    continue
                kind = KINDS[cv.choice.kind]
                options = kind.options(db, cv.choice, character)
                if len(options) == cv.count:
                    kind.save(db, cv.choice, character.id, [o.key for o in options])

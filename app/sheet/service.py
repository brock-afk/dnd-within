from dataclasses import dataclass

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.abilities.rules import modifier
from app.abilities.service import AbilityView, ability_views
from app.characters.models import Character
from app.features.models import Choice
from app.leveling.service import hit_points
from app.sheet.models import (
    CharacterAcEffect,
    CharacterHpEffect,
    CharacterPlayState,
    CharacterPreparedSpell,
    CharacterSpellSlot,
)
from app.sheet.rules import apply_max_change, current_hp, proficiency_bonus
from app.sheet.slots import slot_maximums
from app.spells.models import Spell
from app.spells.queries import character_spells, spellbook


@dataclass
class HpView:
    base: int  # from level history and Constitution
    effects: list[CharacterHpEffect]
    current: int
    temp: int
    temp_source: str | None

    @property
    def maximum(self) -> int:
        return max(0, self.base + sum(e.max_hp_delta for e in self.effects))


def play_state(db: Session, character: Character) -> CharacterPlayState:
    """The character's play state, created (at full HP) the first time it's needed."""
    state = db.get(CharacterPlayState, character.id)
    if state is None:
        state = CharacterPlayState(character_id=character.id, temp_hp=0)
        db.add(state)
    return state


def hp_effects(db: Session, character: Character) -> list[CharacterHpEffect]:
    query = (
        select(CharacterHpEffect)
        .where(CharacterHpEffect.character_id == character.id)
        .order_by(CharacterHpEffect.created_at, CharacterHpEffect.id)
    )
    return list(db.scalars(query))


def max_hp(db: Session, character: Character) -> int | None:
    """Base max HP plus active effects, or None until ability scores are set."""
    base = hit_points(db, character)
    if base is None:
        return None
    return max(0, base.maximum + sum(e.max_hp_delta for e in hp_effects(db, character)))


def hp_view(db: Session, character: Character) -> HpView | None:
    base = hit_points(db, character)
    if base is None:
        return None
    effects = hp_effects(db, character)
    state = db.get(CharacterPlayState, character.id)
    view = HpView(
        base.maximum,
        effects,
        current=0,
        temp=state.temp_hp if state else 0,
        temp_source=state.temp_hp_source if state else None,
    )
    view.current = current_hp(state, view.maximum)
    return view


def track_max_change(db: Session, character: Character, old_max: int | None, heal: bool) -> None:
    """Apply app/sheet/rules.py:apply_max_change after something changed max HP.

    Callers read max_hp() before making their change and pass it in; this reads the new value.
    Does nothing if there was no max HP before (ability scores weren't set). Doesn't commit.
    """
    db.flush()
    new_max = max_hp(db, character)
    if old_max is None or new_max is None or old_max == new_max:
        return
    apply_max_change(play_state(db, character), old_max, new_max, heal)


# --- Abilities, saving throws and Armor Class ---------------------------------------------


@dataclass(frozen=True)
class AbilityRow:
    ability: AbilityView
    save: int  # saving throw bonus
    proficient: bool


def ability_rows(db: Session, character: Character) -> list[AbilityRow] | None:
    """Each ability with its saving throw, or None until scores are set. Save proficiencies
    come from the starting class only (2024 multiclassing rules)."""
    abilities = ability_views(db, character)
    if abilities is None:
        return None
    starting = next((cc for cc in character.classes if cc.is_starting_class), None)
    proficient = set(starting.character_class.saving_throws) if starting else set()
    pb = proficiency_bonus(character.level)
    return [
        AbilityRow(a, a.mod + (pb if a.abbr in proficient else 0), a.abbr in proficient)
        for a in abilities
    ]


@dataclass(frozen=True)
class ArmorClassView:
    base: int  # 10 unarmored, or the highest base effect (Mage Armor 13)
    base_label: str  # "" when unarmored
    dex: int
    effects: list[CharacterAcEffect]

    @property
    def bonuses(self) -> list[CharacterAcEffect]:
        return [e for e in self.effects if e.kind == "bonus"]

    @property
    def total(self) -> int:
        return self.base + self.dex + sum(e.value for e in self.bonuses)


def armor_class(db: Session, character: Character) -> ArmorClassView | None:
    """AC = base (10, or the highest base effect) + DEX modifier + bonus effects. None until
    ability scores are set. Worn armor joins this once inventory exists."""
    abilities = ability_views(db, character)
    if abilities is None:
        return None
    dex = next(a.mod for a in abilities if a.abbr == "DEX")
    effects = list(
        db.scalars(
            select(CharacterAcEffect)
            .where(CharacterAcEffect.character_id == character.id)
            .order_by(CharacterAcEffect.created_at, CharacterAcEffect.id)
        )
    )
    best = max(
        (e for e in effects if e.kind == "base"), key=lambda e: e.value, default=None
    )
    return ArmorClassView(
        best.value if best else 10, best.label if best else "", dex, effects
    )


# --- Spells -------------------------------------------------------------------------------


def _spellcasting_class(character: Character):
    """The character's spellcasting class row (CharacterClassLevel), or None.

    Only one spellcasting class until multiclassing.
    """
    for cc in character.classes:
        if cc.character_class.spellcasting and cc.level >= 1:
            return cc
    return None


def _spellcasting(character: Character) -> tuple[int, dict] | None:
    """(class level, spellcasting rules) of the character's spellcasting class, or None."""
    cc = _spellcasting_class(character)
    return (cc.level, cc.character_class.spellcasting) if cc else None


def prepared_limit(character: Character) -> int | None:
    """How many spells the character can prepare, from their spellcasting class's table."""
    found = _spellcasting(character)
    return found[1]["prepared"][found[0] - 1] if found else None


RITUALS_GROUP = "Rituals · no slot, +10 minutes"


@dataclass(frozen=True)
class CastableSpell:
    spell: Spell
    prepared: bool = False
    # Listed under Rituals: cast as a ritual (10 minutes longer, no slot), never with a slot.
    in_ritual_section: bool = False

    @property
    def group(self) -> str:
        if self.in_ritual_section:
            return RITUALS_GROUP
        return "Cantrips" if self.spell.level == 0 else f"Level {self.spell.level}"

    @property
    def uses_slots(self) -> bool:
        return not self.in_ritual_section and self.spell.level > 0

    @property
    def order(self) -> tuple:
        """Cantrips, then Rituals, then Level 1-9; by name within each."""
        if self.in_ritual_section:
            section = 1
        else:
            section = 0 if self.spell.level == 0 else 1 + self.spell.level
        return (section, self.spell.level, self.spell.name)


def castable_spells(db: Session, character: Character) -> list[CastableSpell]:
    """Everything the character can cast right now: cantrips; every spell castable as a
    ritual (prepared rituals, plus for a Wizard's Ritual Adept the other rituals in the
    spellbook); and prepared spells by level, cast with slots. A prepared ritual is listed
    twice, since it can be cast either way."""
    prepared = prepared_spell_ids(db, character)
    found = _spellcasting(character)
    rituals_from_book = bool(found) and found[1].get("ritual_casting") == "spellbook"

    rows = [
        CastableSpell(cs.spell) for cs in character_spells(db, character.id) if cs.spell.level == 0
    ]
    for entry in spellbook(db, character.id):
        is_prepared = entry.spell_id in prepared
        if is_prepared:
            rows.append(CastableSpell(entry.spell, prepared=True))
        if entry.spell.ritual and (is_prepared or rituals_from_book):
            rows.append(CastableSpell(entry.spell, prepared=is_prepared, in_ritual_section=True))
    return sorted(rows, key=lambda r: r.order)


# --- Spell slots --------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotLevel:
    level: int
    maximum: int
    expended: int

    @property
    def remaining(self) -> int:
        return self.maximum - min(self.expended, self.maximum)


def spell_slots(db: Session, character: Character) -> dict[int, SlotLevel]:
    """{slot level: SlotLevel} for the character's spellcasting class; empty if none."""
    found = _spellcasting(character)
    if not found:
        return {}
    class_level, spellcasting = found
    maximums = slot_maximums(spellcasting.get("slots", "full"), class_level)
    used = {
        row.slot_level: row.expended
        for row in db.scalars(
            select(CharacterSpellSlot).where(CharacterSpellSlot.character_id == character.id)
        )
    }
    return {lvl: SlotLevel(lvl, mx, used.get(lvl, 0)) for lvl, mx in maximums.items()}


def set_slots_remaining(db: Session, character: Character, level: int, remaining: int) -> None:
    """Record that `remaining` slots of this level are left (the caller validated it)."""
    maximum = spell_slots(db, character)[level].maximum
    row = db.get(CharacterSpellSlot, (character.id, level))
    if row is None:
        row = CharacterSpellSlot(character_id=character.id, slot_level=level, expended=0)
        db.add(row)
    row.expended = maximum - remaining


def prepared_spell_ids(db: Session, character: Character) -> set[int]:
    query = select(CharacterPreparedSpell.spell_id).where(
        CharacterPreparedSpell.character_id == character.id
    )
    return set(db.scalars(query))


def ability_modifier(db: Session, character: Character, abbr: str) -> int:
    """Final modifier for an ability (base + bonuses); 0 if scores aren't set."""
    abilities = ability_views(db, character) or []
    found = next((a for a in abilities if a.abbr == abbr), None)
    return modifier(found.total) if found else 0


def _rule_warnings(cc, highest_slot: int, spell: Spell) -> list[str]:
    found = []
    if cc.class_id not in {c.id for c in spell.classes}:
        found.append(f"Not on the {cc.character_class.name} list")
    if spell.level > highest_slot:
        found.append("Above your slot level")
    return found


def spell_warnings(db: Session, character: Character) -> dict[int, list[str]]:
    """{spell id: warnings} for spellbook spells that break the usual rules. Any spell can be
    copied into a spellbook, but these get a marker. Calculated, never stored, so they clear
    on their own (e.g. a high-level spell once the character gains the slots)."""
    return {
        spell.id: found
        for spell, found in copy_warnings(
            db, character, [entry.spell for entry in spellbook(db, character.id)]
        ).items()
        if found
    }


def copy_warnings(db: Session, character: Character, spells: list[Spell]) -> dict:
    """{spell: warnings} the spells would get in this character's spellbook."""
    cc = _spellcasting_class(character)
    if cc is None:
        return {spell: [] for spell in spells}
    highest_slot = max(spell_slots(db, character), default=0)
    return {spell: _rule_warnings(cc, highest_slot, spell) for spell in spells}


def spellbook_notes(db: Session, character: Character) -> dict[int, str]:
    """{spell id: note} for spellbook spells that didn't come from a level up: copied ones
    ("Copied to spellbook · scroll from the crypt") and ones a feature added ("From Evocation
    Savant")."""
    notes = {}
    for entry in spellbook(db, character.id):
        if entry.acquired_via == "copied":
            notes[entry.spell_id] = " · ".join(
                filter(None, ["Copied to spellbook", entry.source_note])
            )
        elif entry.acquired_via == "feature" and entry.choice_id is not None:
            notes[entry.spell_id] = f"From {db.get(Choice, entry.choice_id).feature.name}"
    return notes


COPY_SEARCH_MIN = 2  # characters typed before searching
COPY_SEARCH_LIMIT = 8


def search_copyable(db: Session, query: str) -> list[Spell]:
    """Level 1+ spells (cantrips aren't written in spellbooks) whose name contains `query`:
    names starting with it first, then by name."""
    query = query.strip()
    if len(query) < COPY_SEARCH_MIN:
        return []
    starts = case((Spell.name.istartswith(query, autoescape=True), 0), else_=1)
    return list(
        db.scalars(
            select(Spell)
            .where(
                Spell.level >= 1,
                Spell.retired_at.is_(None),
                Spell.name.icontains(query, autoescape=True),
            )
            .order_by(starts, Spell.name)
            .limit(COPY_SEARCH_LIMIT)
        )
    )

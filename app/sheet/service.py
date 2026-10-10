from dataclasses import dataclass

from sqlalchemy import case, delete, select
from sqlalchemy.orm import Session

from app.abilities.rules import ABILITIES, modifier
from app.abilities.service import AbilityView, ability_views
from app.characters.models import Character
from app.content.queries import available
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature, FeatureSpell
from app.features.service import applicable_choice, feature_groups
from app.leveling.service import hit_points
from app.sheet.models import (
    CharacterAcEffect,
    CharacterHpEffect,
    CharacterPlayState,
    CharacterPreparedSpell,
    CharacterSpellSlot,
)
from app.sheet.rules import apply_max_change, current_hp, proficiency_bonus, skill_bonus
from app.skills.models import CharacterSkill, CharacterSkillExpertise, Skill
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
    # Where the save proficiency comes from, e.g. ("Wizard",) or ("Transmuter's Stone",).
    sources: tuple[str, ...] = ()


def _grant_sources(db: Session, character: Character) -> list[tuple[str, dict]]:
    """(source name, grants) for everything giving the character attributes: features they
    have, and picked options (only while picked, like the Transmuter's Stone benefit)."""
    found = [
        (fv.feature.name, fv.feature.grants)
        for group in feature_groups(db, character)
        for fv in group.features
        if fv.feature.grants
    ]
    picks = db.execute(
        select(ChoiceOption.grants, Choice)
        .join(CharacterChoicePick, CharacterChoicePick.option_id == ChoiceOption.id)
        .join(Choice, Choice.id == ChoiceOption.choice_id)
        .where(CharacterChoicePick.character_id == character.id, ChoiceOption.grants.is_not(None))
    )
    for grants, choice in picks:
        if applicable_choice(db, character, choice.id) is not None:
            found.append((choice.feature.name, grants))
    return found


def _by_source(sources: dict[str, list[str]], order: list[str]) -> list[tuple[list[str], str]]:
    """{item: [sources]} regrouped as ([items], "source, source"), in `order`, so the sheet
    can say "Intelligence, Wisdom · Wizard"."""
    groups: dict[str, list[str]] = {}
    for item in order:
        if item in sources:
            groups.setdefault(", ".join(sources[item]), []).append(item)
    return [(items, label) for label, items in groups.items()]


@dataclass(frozen=True)
class Attributes:
    """Passive character data for the Play sheet, each part with where it comes from."""

    saves: dict[str, list[str]]  # ability abbreviation -> sources
    speed: int  # walking speed in feet
    speed_parts: list[str]  # ["35 Goliath", "+10 Transmuter's Stone"]
    darkvision: int  # range in feet; 0 without Darkvision
    darkvision_sources: list[str]
    resistances: dict[str, list[str]]  # damage type -> sources

    @property
    def save_groups(self) -> list[tuple[list[str], str]]:
        names = {a.abbr: a.name for a in ABILITIES}
        return [
            ([names[abbr] for abbr in abbrs], label)
            for abbrs, label in _by_source(self.saves, [a.abbr for a in ABILITIES])
        ]

    @property
    def resistance_groups(self) -> list[tuple[list[str], str]]:
        return [
            ([t.title() for t in types], label)
            for types, label in _by_source(self.resistances, sorted(self.resistances))
        ]


def attributes(db: Session, character: Character) -> Attributes:
    """Saves (the starting class's, by 2024 multiclassing rules, plus granted ones), speed
    (the species' plus bonuses), Darkvision (the best range plus bonuses) and resistances."""
    saves: dict[str, list[str]] = {}
    starting = next((cc for cc in character.classes if cc.is_starting_class), None)
    if starting:
        for abbr in starting.character_class.saving_throws:
            saves.setdefault(abbr, []).append(starting.character_class.name)

    speed = character.species.speed
    speed_parts = [f"{speed} {character.species.name}"]
    ranges: list[tuple[int, str]] = []
    bonuses: list[tuple[int, str]] = []
    resistances: dict[str, list[str]] = {}
    for source, grants in _grant_sources(db, character):
        for abbr in grants.get("save_proficiencies", []):
            saves.setdefault(abbr, []).append(source)
        for damage_type in grants.get("resistances", []):
            resistances.setdefault(damage_type, []).append(source)
        if grants.get("speed_bonus"):
            speed += grants["speed_bonus"]
            speed_parts.append(f"+{grants['speed_bonus']} {source}")
        if grants.get("darkvision"):
            ranges.append((grants["darkvision"], source))
        if grants.get("darkvision_bonus"):
            bonuses.append((grants["darkvision_bonus"], source))

    best = max(ranges, default=(0, ""))
    darkvision = best[0] + sum(n for n, _ in bonuses)
    darkvision_sources = ([best[1]] if best[1] else []) + [source for _, source in bonuses]
    return Attributes(saves, speed, speed_parts, darkvision, darkvision_sources, resistances)


def ability_rows(
    db: Session, character: Character, attrs: Attributes | None = None
) -> list[AbilityRow] | None:
    """Each ability with its saving throw, or None until scores are set. Pass `attrs` if
    they're already worked out."""
    abilities = ability_views(db, character)
    if abilities is None:
        return None
    sources = (attrs or attributes(db, character)).saves
    pb = proficiency_bonus(character.level)
    return [
        AbilityRow(
            a, a.mod + (pb if a.abbr in sources else 0), a.abbr in sources,
            tuple(sources.get(a.abbr, ())),
        )
        for a in abilities
    ]


@dataclass(frozen=True)
class SkillRow:
    skill: Skill
    bonus: int
    proficient: bool
    expertise: bool
    expertise_source: str = ""  # the feature that gave it, e.g. "Scholar"


def skill_rows(db: Session, character: Character) -> list[SkillRow] | None:
    """Every skill with the character's bonus, or None until ability scores are set."""
    abilities = ability_views(db, character)
    if abilities is None:
        return None
    mods = {a.abbr: a.mod for a in abilities}
    pb = proficiency_bonus(character.level)
    proficient = set(
        db.scalars(select(CharacterSkill.skill_id).where(CharacterSkill.character_id == character.id))
    )
    expertise = {
        row.skill_id: row
        for row in db.scalars(
            select(CharacterSkillExpertise).where(
                CharacterSkillExpertise.character_id == character.id
            )
        )
    }
    rows = []
    for skill in db.scalars(select(Skill).where(available(Skill)).order_by(Skill.name)):
        is_proficient = skill.id in proficient
        found = expertise.get(skill.id) if is_proficient else None
        source = db.get(Choice, found.choice_id).feature.name if found and found.choice_id else ""
        rows.append(
            SkillRow(
                skill,
                skill_bonus(mods.get(skill.ability, 0), pb, is_proficient, found is not None),
                is_proficient,
                found is not None,
                source,
            )
        )
    return rows


@dataclass(frozen=True)
class ArmorClassView:
    base: int  # 10 unarmored, or the highest base effect (Mage Armor 13)
    base_label: str  # "No armor", or the base effect's name ("Mage Armor")
    dex: int
    effects: list[CharacterAcEffect]

    @property
    def bonuses(self) -> list[CharacterAcEffect]:
        return [e for e in self.effects if e.kind == "bonus"]

    @property
    def minimum(self) -> CharacterAcEffect | None:
        """The highest "AC can't be lower than" effect (Barkskin 17)."""
        return max(
            (e for e in self.effects if e.kind == "minimum"), key=lambda e: e.value, default=None
        )

    @property
    def calculated(self) -> int:
        return self.base + self.dex + sum(e.value for e in self.bonuses)

    @property
    def minimum_wins(self) -> bool:
        return self.minimum is not None and self.minimum.value > self.calculated

    @property
    def total(self) -> int:
        return self.minimum.value if self.minimum_wins else self.calculated

    @property
    def breakdown(self) -> str:
        """How the total is reached: "No armor 10 + 2 DEX", "Mage Armor 13 + 2 DEX + 2 Shield
        of Faith", or "Barkskin 17 (minimum)" when a minimum beats the calculation."""
        if self.minimum_wins:
            return f"{self.minimum.label} {self.minimum.value} (minimum)"
        parts = [(self.dex, "DEX"), *((e.value, e.label) for e in self.bonuses)]
        return f"{self.base_label} {self.base}" + "".join(
            f" {'+' if value >= 0 else '−'} {abs(value)} {label}" for value, label in parts
        )


def armor_class(db: Session, character: Character) -> ArmorClassView | None:
    """AC = base (10, or the highest base effect) + DEX modifier + bonus effects, raised to the
    highest minimum effect. None until ability scores are set. Worn armor joins this once
    inventory exists."""
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
    best = max((e for e in effects if e.kind == "base"), key=lambda e: e.value, default=None)
    return ArmorClassView(best.value if best else 10, best.label if best else "No armor", dex, effects)


@dataclass(frozen=True)
class AcSpell:
    """A prepared spell that changes AC (its content declares `ac_effect`), offered on the AC
    card to cast on yourself."""

    spell: Spell
    slots: list["SlotLevel"]  # the slot levels it can be cast with right now

    @property
    def effect(self) -> dict:
        return self.spell.details["ac_effect"]


def ac_spells(db: Session, character: Character) -> list[AcSpell]:
    """Prepared spells with an AC effect, each with its usable slot levels. Spells whose effect
    is already active are left out: it's listed with an End button instead."""
    slots = spell_slots(db, character)
    active = set(
        db.scalars(
            select(CharacterAcEffect.spell_id).where(
                CharacterAcEffect.character_id == character.id,
                CharacterAcEffect.spell_id.is_not(None),
            )
        )
    )
    return [
        AcSpell(
            row.spell,
            [s for s in slots.values() if s.level >= row.spell.level and s.remaining > 0],
        )
        for row in castable_spells(db, character)
        if row.uses_slots and row.spell.details.get("ac_effect") and row.spell.id not in active
    ]


def _ends_on_long_rest(spell: Spell) -> bool:
    """Spells lasting 8 hours or less are over by the end of a long rest."""
    duration = spell.details.get("duration", {})
    if duration.get("kind") != "timed":
        return False
    return duration["unit"] in ("round", "minute") or (
        duration["unit"] == "hour" and duration["amount"] <= 8
    )


def apply_ac_spell(db: Session, character: Character, spell: Spell) -> None:
    """Add the spell's AC effect, replacing one from an earlier casting (recasting refreshes,
    never stacks). The caller spends the slot."""
    db.execute(
        delete(CharacterAcEffect).where(
            CharacterAcEffect.character_id == character.id,
            CharacterAcEffect.spell_id == spell.id,
        )
    )
    effect = spell.details["ac_effect"]
    db.add(
        CharacterAcEffect(
            character_id=character.id,
            label=spell.name,
            kind=effect["kind"],
            value=effect["value"],
            spell_id=spell.id,
            ends_on_long_rest=_ends_on_long_rest(spell),
        )
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
    # The feature that keeps it always prepared (Wondrous Alteration), and whether one cast
    # can spend a use of that feature instead of a slot.
    granted_by: Feature | None = None
    free_cast: bool = False
    note: str = ""  # from the granting feature, e.g. what Wondrous Alteration adds

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
    granted = granted_spells(db, character)

    rows = [
        CastableSpell(cs.spell) for cs in character_spells(db, character.id) if cs.spell.level == 0
    ]
    for entry in spellbook(db, character.id):
        if entry.spell_id in granted:
            continue  # listed below as always prepared
        is_prepared = entry.spell_id in prepared
        if is_prepared:
            rows.append(CastableSpell(entry.spell, prepared=True))
        if entry.spell.ritual and (is_prepared or rituals_from_book):
            rows.append(CastableSpell(entry.spell, prepared=is_prepared, in_ritual_section=True))
    for feature_spell, feature in granted.values():
        spell = feature_spell.spell
        rows.append(
            CastableSpell(
                spell,
                prepared=True,
                granted_by=feature,
                free_cast=feature_spell.free_cast,
                note=feature_spell.note or "",
            )
        )
        if spell.ritual:
            rows.append(CastableSpell(spell, prepared=True, in_ritual_section=True))
    return sorted(rows, key=lambda r: r.order)


def granted_spells(db: Session, character: Character) -> dict[int, tuple[FeatureSpell, Feature]]:
    """{spell id: (its FeatureSpell, the feature)} for spells the character's features keep
    always prepared. They don't count toward the prepare limit."""
    return {
        fs.spell_id: (fs, fv.feature)
        for group in feature_groups(db, character)
        for fv in group.features
        for fs in fv.feature.spells
        if fs.spell.retired_at is None
    }


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
                available(Spell),
                Spell.name.icontains(query, autoescape=True),
            )
            .order_by(starts, Spell.name)
            .limit(COPY_SEARCH_LIMIT)
        )
    )

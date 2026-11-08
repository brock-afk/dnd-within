import math
from dataclasses import dataclass, field, replace

from sqlalchemy import Select, case, select
from sqlalchemy.orm import Session

from app.abilities.queries import AbilityView, ability_views
from app.abilities.rules import ABILITIES, modifier
from app.auth.models import User
from app.characters.models import Character
from app.classes.models import CharacterClass
from app.content.queries import available, picked_row
from app.core.db import reload_all
from app.features.kinds import KINDS, OptionView, owner_level, source_name
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature, FeatureSpell
from app.features.queries import (
    FeatureGroup,
    PlayChoice,
    always_prepared_reasons,
    always_prepared_spells,
    applicable_choice,
    feature_groups,
    play_choices,
)
from app.inventory.models import CharacterItem, Item
from app.inventory.queries import (
    HealingUse,
    ac_scrolls,
    coin_summary,
    coin_values,
    healing_uses,
    inventory,
    item_features,
)
from app.inventory.queries import digest as inventory_digest
from app.leveling.queries import hit_points
from app.sharing.models import CharacterShare
from app.sharing.service import public_share
from app.sheet.models import (
    CharacterAcEffect,
    CharacterFeatureUse,
    CharacterHitDice,
    CharacterHpEffect,
    CharacterPlayState,
    CharacterPreparedSpell,
    CharacterSpellSlot,
)
from app.sheet.rules import current_hp, proficiency_bonus, skill_bonus, uses_maximum
from app.sheet.slots import slot_kind, slot_maximums
from app.skills.models import CharacterSkill, CharacterSkillExpertise, Skill
from app.spells.models import Spell
from app.spells.queries import character_spells, pickable_spells, spellbook


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


# --- Abilities, saving throws and Armor Class ---------------------------------------------


@dataclass(frozen=True)
class AbilityRow:
    ability: AbilityView
    save: int  # saving throw bonus
    proficient: bool
    # Where the save proficiency comes from, e.g. ("Wizard",) or ("Transmuter's Stone",).
    sources: tuple[str, ...] = ()


def _grant_label(db: Session, feature: Feature) -> str:
    """Where a benefit comes from, as the sheet names it: the feature ("Transmuter's Stone"),
    or for a magic item the item itself, not its "While attuned" feature."""
    return db.get(Item, feature.item_id).name if feature.item_id else feature.name


def _grant_sources(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> list[tuple[str, dict]]:
    """(source name, grants) for everything giving the character attributes: features they
    have, and picked options (only while picked, like the Transmuter's Stone benefit)."""
    found = [
        (_grant_label(db, fv.feature), fv.feature.grants)
        for group in (feature_groups(db, character) if groups is None else groups)
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
            found.append((_grant_label(db, choice.feature), grants))
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
    tools: dict[str, list[str]]  # tool name -> sources

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

    @property
    def tool_groups(self) -> list[tuple[list[str], str]]:
        return _by_source(self.tools, sorted(self.tools))


# --- Features and placed traits ------------------------------------------------------------


@dataclass(frozen=True)
class FeatureEntry:
    """A feature or picked option to read on the Play sheet: in Features, or in a row of
    Attributes."""

    name: str
    source: str  # "Warlock", "Tiefling", or the choice it was picked in ("Eldritch Invocations")
    summary: str
    description: str = ""  # a feature's full rules text, where the pack has it


@dataclass(frozen=True)
class FeatureRow:
    """One row of the Features section: a feature with uses to track (pips), an ability that
    spends those uses (`spender`, with `uses` its pool: a magic item's charges), a choice made
    in play (the Transmuter's Stone benefit), or a feature or picked option to read."""

    uses: FeatureUses | None = None
    spender: Feature | None = None
    choice: PlayChoice | None = None
    entry: FeatureEntry | None = None
    source: str = ""  # for uses and spender rows: "Warlock", "Tome of Bal'vir"

    @property
    def name(self) -> str:
        """A tracked feature's name without its source repeated: a homebrew item's "Tome of
        Bal'vir charges" is "Charges", next to "· Tome of Bal'vir"."""
        if self.spender:
            return self.spender.name
        name = self.uses.feature.name
        if self.source and name.startswith(self.source + " "):
            rest = name[len(self.source) + 1 :]
            return rest[:1].upper() + rest[1:]
        return name

    @property
    def digest(self) -> str:
        if self.spender:
            return self.spender.name
        if self.uses:
            return f"{self.name} {self.uses.remaining}/{self.uses.maximum}"
        if self.choice:
            return self.choice.picked.name
        return self.entry.name


@dataclass(frozen=True)
class SheetFeatures:
    groups: list[tuple[str, list[FeatureRow]]]  # ("Bonus Actions", rows), in turn order
    traits: dict[str, list[FeatureEntry]]  # passive ones by Attributes row: "senses", "saves"...

    @property
    def digest(self) -> str:
        """The collapsed section's summary: every row's name, with uses left on tracked ones."""
        return " · ".join(row.digest for _, rows in self.groups for row in rows)


FEATURE_GROUPS = [
    ("action", "Actions"),
    ("bonus_action", "Bonus Actions"),
    ("reaction", "Reactions"),
    ("triggered", "Triggered"),
    (None, "Other"),
]


def _shown_elsewhere(feature: Feature) -> bool:
    """Not a row of its own: slot recovery (the Short rest panel), spending another feature's
    uses (listed under that feature), or a magic item's ability without uses (Inventory)."""
    return bool(feature.slot_recovery or feature.spends_feature_id or feature.item_id)


def _action_group(action: str | None, when: str | None) -> str | None:
    """Its group: what using it takes, "triggered" with only a `when`, else None."""
    return action or ("triggered" if when else None)


def _uses_group(uses: FeatureUses) -> str | None:
    """A tracked feature's group: its own action or `when`; else its picked option's (Giant
    Ancestry's Stone's Endurance is a Reaction); else the casting time of the spell its uses
    cast for free (Infernal Legacy's Hellish Rebuke). A pool other abilities spend, anything
    longer, or nothing, is Other."""
    feature = uses.feature
    if group := _action_group(feature.action, feature.when):
        return group
    for option in uses.options:
        if group := _action_group(option.action, option.when):
            return group
    if uses.spenders:  # a pool other abilities spend (an item's charges): each has its own row
        return None
    units = {fs.spell.casting_unit for fs in feature.spells if fs.free_cast}
    unit = units.pop() if len(units) == 1 else None
    return unit if unit in ("action", "bonus_action", "reaction") else None


def sheet_features(
    db: Session,
    character: Character,
    groups: list[FeatureGroup],
    uses: list[FeatureUses],
    play_choices: list[PlayChoice],
) -> SheetFeatures:
    """The Play sheet's Features section, grouped by what using each row takes, and the
    passive features placed in Attributes rows (Devil's Sight with Senses). Rows are features
    with uses, choices made in play, and features or picked options whose content gives an
    `action` or a `when` (Pact of the Blade, Dark One's Blessing). Untagged ones, like a
    Tiefling's Size, are for the Build page. Picked options of a feature with uses show in its
    row."""
    tracked = {u.feature.id: u for u in uses if not u.rest_only}
    in_play = {pc.choice.id: pc for pc in play_choices if pc.picked}
    found: list[tuple[str | None, FeatureRow]] = []
    traits: dict[str, list[FeatureEntry]] = {}

    def place(action: str | None, when: str | None, sheet: str | None, entry: FeatureEntry):
        if group := _action_group(action, when):
            found.append((group, FeatureRow(entry=entry)))
        elif sheet:
            traits.setdefault(sheet, []).append(entry)

    for group in groups:
        for fv in group.features:
            feature = fv.feature
            if pool := tracked.get(feature.id):
                source = source_name(db, feature)
                found.append((_uses_group(pool), FeatureRow(uses=pool, source=source)))
                # Abilities spending these uses go by what using them takes (Bonus Actions…).
                for f in pool.spenders:
                    row = FeatureRow(uses=pool, spender=f, source=source_name(db, f))
                    found.append((_action_group(f.action, f.when), row))
            elif not feature.uses and not _shown_elsewhere(feature):
                source = source_name(db, feature)
                entry = FeatureEntry(
                    feature.name, source, feature.summary, feature.description or ""
                )
                place(feature.action, feature.when, feature.sheet, entry)
            for cv in fv.choices:
                if cv.choice.id in in_play:
                    found.append((None, FeatureRow(choice=in_play[cv.choice.id])))
                if cv.choice.kind != "option" or cv.choice.in_play or feature.uses:
                    continue
                keys = {o.key for o in cv.picked}
                for o in cv.choice.options:
                    if str(o.id) in keys:
                        entry = FeatureEntry(o.name, cv.choice.name, o.summary)
                        place(o.action, o.when, o.sheet, entry)
    return SheetFeatures(
        [
            (label, rows)
            for key, label in FEATURE_GROUPS
            if (rows := [row for group, row in found if group == key])
        ],
        traits,
    )


def attributes(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> Attributes:
    """Saves (the starting class's, by 2024 multiclassing rules, plus granted ones), speed
    (the species' plus bonuses), Darkvision (the best range plus bonuses) and resistances.
    Pass `groups` if they're already worked out."""
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
    tools: dict[str, list[str]] = {}
    for source, grants in _grant_sources(db, character, groups):
        for abbr in grants.get("save_proficiencies", []):
            saves.setdefault(abbr, []).append(source)
        for damage_type in grants.get("resistances", []):
            resistances.setdefault(damage_type, []).append(source)
        for tool in grants.get("tool_proficiencies", []):
            tools.setdefault(tool, []).append(source)
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
    return Attributes(saves, speed, speed_parts, darkvision, darkvision_sources, resistances, tools)


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
            a,
            a.mod + (pb if a.abbr in sources else 0),
            a.abbr in sources,
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
        db.scalars(
            select(CharacterSkill.skill_id).where(CharacterSkill.character_id == character.id)
        )
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
    # Always-on bonuses from features and items, like a magic item's +1: (value, source). Not
    # effects, so they aren't ended from the AC card; they go when the item is unattuned.
    granted: list[tuple[int, str]] = field(default_factory=list)

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
        return (
            self.base
            + self.dex
            + sum(e.value for e in self.bonuses)
            + sum(value for value, _ in self.granted)
        )

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
        parts = [(self.dex, "DEX"), *self.granted, *((e.value, e.label) for e in self.bonuses)]
        return f"{self.base_label} {self.base}" + "".join(
            f" {'+' if value >= 0 else '−'} {abs(value)} {label}" for value, label in parts
        )


def armor_class(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> ArmorClassView | None:
    """AC = base (10, or the highest base effect) + DEX modifier + bonus effects and granted
    bonuses (a magic item's +1), raised to the highest minimum effect. None until ability
    scores are set. Worn armor will join this once the sheet does armor. Pass `groups` if
    they're already worked out."""
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
    granted = [
        (grants["ac_bonus"], source)
        for source, grants in _grant_sources(db, character, groups)
        if grants.get("ac_bonus")
    ]
    base, label = (best.value, best.label) if best else (10, "No armor")
    return ArmorClassView(base, label, dex, effects, granted)


@dataclass(frozen=True)
class AcSpell:
    """A prepared spell that changes AC (its content declares `ac_effect`), offered on the AC
    card to cast on yourself."""

    spell: Spell
    slots: list[SlotLevel]  # the slot levels it can be cast with right now
    at_will_from: str = ""  # the feature that casts it at will, without a slot

    @property
    def effect(self) -> dict:
        return self.spell.details["ac_effect"]


def active_ac_spell_ids(db: Session, character: Character) -> set[int]:
    """Spells whose AC effect is on right now (Mage Armor cast, or read from a scroll)."""
    return set(
        db.scalars(
            select(CharacterAcEffect.spell_id).where(
                CharacterAcEffect.character_id == character.id,
                CharacterAcEffect.spell_id.is_not(None),
            )
        )
    )


def ac_spells(
    db: Session,
    character: Character,
    castable: list[CastableSpell] | None = None,
    slots: dict[int, SlotLevel] | None = None,
) -> list[AcSpell]:
    """Spells with an AC effect the character can cast on themselves: prepared ones, with
    their usable slot levels, and ones a feature casts at will (Armor of Shadows), once each.
    Spells whose effect is already active are left out: it's listed with an End button
    instead. Pass `castable` and `slots` if they're already worked out."""
    if castable is None:
        castable = castable_spells(db, character)
    if slots is None:
        slots = spell_slots(db, character)
    active = active_ac_spell_ids(db, character)
    found: dict[int, AcSpell] = {}
    for row in castable:
        spell = row.spell
        if not spell.details.get("ac_effect") or spell.id in active:
            continue
        if not (row.uses_slots or row.at_will):
            continue
        ac = found.setdefault(spell.id, AcSpell(spell, []))
        if row.uses_slots:
            usable = [s for s in slots.values() if s.level >= spell.level and s.remaining > 0]
            found[spell.id] = replace(ac, slots=usable)
        if row.at_will:
            found[spell.id] = replace(found[spell.id], at_will_from=row.granted_by.name)
    return list(found.values())


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
    """How many spells the character can prepare from their spellbook, from their spellcasting
    class's table; None for a class without one (its spells are picked on level up)."""
    found = _spellcasting(character)
    table = found[1].get("prepared") if found else None
    return table[found[0] - 1] if table else None


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
    charge_cost: int = 1  # uses of `granted_by` a free cast spends
    # Cast only by spending the feature's uses, never with slots (a magic item's spell).
    charge_only: bool = False
    item_name: str = ""  # granted by a magic item: tagged with its name ("Tome of Bal'vir")
    note: str = ""  # from the granting feature, e.g. what Wondrous Alteration adds

    @property
    def group(self) -> str:
        if self.in_ritual_section:
            return RITUALS_GROUP
        return "Cantrips" if self.spell.level == 0 else f"Level {self.spell.level}"

    @property
    def uses_slots(self) -> bool:
        return not self.in_ritual_section and self.spell.level > 0 and not self.charge_only

    @property
    def at_will(self) -> bool:
        """Cast free with no limit: the granting feature has no uses to spend (Armor of
        Shadows' Mage Armor)."""
        return self.free_cast and self.granted_by is not None and self.granted_by.uses is None

    @property
    def free_label(self) -> str:
        """The free-cast option: "Free · Wondrous Alteration", or for a magic item's charges
        "2 charges · Embercleave Charm"."""
        feature = self.granted_by
        if feature.item_id:
            cost = f"{self.charge_cost} charge{'s' if self.charge_cost != 1 else ''}"
            return f"{cost} · {feature.name.removesuffix(' charges')}"
        return f"Free · {feature.name}"

    @property
    def order(self) -> tuple:
        """Cantrips, then Rituals, then Level 1-9; by name within each."""
        if self.in_ritual_section:
            section = 1
        else:
            section = 0 if self.spell.level == 0 else 1 + self.spell.level
        return (section, self.spell.level, self.spell.name)


def castable_spells(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> list[CastableSpell]:
    """Everything the character can cast right now: cantrips; every spell castable as a
    ritual (prepared rituals, plus for a Wizard's Ritual Adept the other rituals in the
    spellbook); and prepared spells by level (from the spellbook, or picked on level up), cast
    with slots. A prepared ritual is listed
    twice, since it can be cast either way. Pass `groups` if they're already worked out."""
    prepared = prepared_spell_ids(db, character)
    found = _spellcasting(character)
    rituals_from_book = bool(found) and found[1].get("ritual_casting") == "spellbook"
    granted = granted_spells(db, character, groups)

    rows = []
    picked = set()
    for cs in character_spells(db, character.id):
        picked.add(cs.spell_id)
        if cs.spell.level == 0:
            rows.append(CastableSpell(cs.spell))
        elif not (cs.spell_id in granted and granted[cs.spell_id][0].always_prepared):
            # Spells picked on level up (a Warlock's) are its prepared list.
            rows.append(CastableSpell(cs.spell, prepared=True))
            if cs.spell.ritual:
                rows.append(CastableSpell(cs.spell, prepared=True, in_ritual_section=True))
    for entry in spellbook(db, character.id):
        if entry.spell_id in granted and granted[entry.spell_id][0].always_prepared:
            continue  # listed below as always prepared
        if entry.spell_id in picked:
            continue  # already listed as picked (Magic Initiate's pick also in the book)
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
                prepared=feature_spell.always_prepared,
                granted_by=feature,
                free_cast=feature_spell.free_cast,
                charge_cost=feature_spell.charge_cost,
                charge_only=not feature_spell.always_prepared,
                item_name=db.get(Item, feature.item_id).name if feature.item_id else "",
                note=feature_spell.note or "",
            )
        )
        if spell.ritual and feature_spell.always_prepared:
            rows.append(CastableSpell(spell, prepared=True, in_ritual_section=True))
    return sorted(rows, key=lambda r: r.order)


def granted_spells(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> dict[int, tuple[FeatureSpell, Feature]]:
    """{spell id: (its FeatureSpell, the feature)} for spells the character's features give:
    always prepared ones (which don't count toward the prepare limit), and ones cast only by
    spending a feature's uses (`always_prepared` off)."""
    return {
        fs.spell_id: (fs, fv.feature)
        for group in (feature_groups(db, character) if groups is None else groups)
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
    kind: str = "spellcasting"  # or "pact": Pact Magic, back on a short rest

    @property
    def remaining(self) -> int:
        return self.maximum - min(self.expended, self.maximum)


def spell_slots(db: Session, character: Character) -> dict[int, SlotLevel]:
    """{slot level: SlotLevel} for the character's spellcasting class; empty if none."""
    found = _spellcasting(character)
    if not found:
        return {}
    class_level, spellcasting = found
    progression = spellcasting.get("slots", "full")
    kind = slot_kind(progression)
    used = {
        row.slot_level: row.expended
        for row in db.scalars(
            select(CharacterSpellSlot).where(
                CharacterSpellSlot.character_id == character.id, CharacterSpellSlot.kind == kind
            )
        )
    }
    return {
        lvl: SlotLevel(lvl, mx, used.get(lvl, 0), kind)
        for lvl, mx in slot_maximums(progression, class_level).items()
    }


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


def _copyable_spells(user_id: int) -> Select[tuple[Spell]]:
    # Cantrips aren't written in spellbooks.
    return pickable_spells(user_id).where(Spell.level >= 1)


def search_copyable(db: Session, query: str, user_id: int) -> list[Spell]:
    query = query.strip()
    if len(query) < COPY_SEARCH_MIN:
        return []
    starts = case((Spell.name.istartswith(query, autoescape=True), 0), else_=1)
    return list(
        db.scalars(
            _copyable_spells(user_id)
            .where(Spell.name.icontains(query, autoescape=True))
            .order_by(starts, Spell.name)
            .limit(COPY_SEARCH_LIMIT)
        )
    )


# --- Limited-use features -----------------------------------------------------------------


@dataclass(frozen=True)
class FeatureUses:
    feature: Feature
    maximum: int
    expended: int
    class_level: int  # the owning class's level (character level for species features)
    # The options the character picked for this feature's choices (e.g. Stone's Endurance for
    # Giant Ancestry), which say what a use actually does and when.
    options: tuple[ChoiceOption, ...] = ()
    # Features that spend these uses when used, like a magic item's Stonecunning (its charges).
    spenders: tuple[Feature, ...] = ()

    @property
    def remaining(self) -> int:
        return self.maximum - min(self.expended, self.maximum)

    @property
    def recharge(self) -> str:
        return self.feature.uses["recharge"]

    @property
    def rest_only(self) -> bool:
        """Used only during a rest (like Arcane Recovery), so it lives in the rest panel."""
        return self.feature.slot_recovery is not None


def feature_uses(
    db: Session, character: Character, groups: list[FeatureGroup] | None = None
) -> list[FeatureUses]:
    """Every limited-use feature the character has (respecting level, class, subclass and
    species, exactly like the character page). Pass `groups` if they're already worked out."""
    spent = {
        row.feature_id: row.expended
        for row in db.scalars(
            select(CharacterFeatureUse).where(CharacterFeatureUse.character_id == character.id)
        )
    }
    picked: dict[int, list[ChoiceOption]] = {}
    for option, feature_id in db.execute(
        select(ChoiceOption, Choice.feature_id)
        .join(CharacterChoicePick, CharacterChoicePick.option_id == ChoiceOption.id)
        .join(Choice, Choice.id == ChoiceOption.choice_id)
        .where(CharacterChoicePick.character_id == character.id)
        .order_by(ChoiceOption.position)
    ):
        picked.setdefault(feature_id, []).append(option)

    if groups is None:
        groups = feature_groups(db, character)
    spenders: dict[int, list[Feature]] = {}
    for group in groups:
        for fv in group.features:
            if fv.feature.spends_feature_id:
                spenders.setdefault(fv.feature.spends_feature_id, []).append(fv.feature)

    result = []
    for group in groups:
        for fv in group.features:
            feature = fv.feature
            if not feature.uses:
                continue
            level = owner_level(db, character, feature)
            options = tuple(picked.get(feature.id, ()))
            result.append(
                FeatureUses(
                    feature,
                    uses_maximum(feature.uses["max"], character.level),
                    spent.get(feature.id, 0),
                    level,
                    options,
                    tuple(spenders.get(feature.id, ())),
                )
            )
    return result


@dataclass(frozen=True)
class Spender:
    uses: FeatureUses  # the pool it spends, like the item's charges
    feature: Feature


def uses_of(db: Session, character: Character, feature_id: int | None) -> FeatureUses | None:
    return next((u for u in feature_uses(db, character) if u.feature.id == feature_id), None)


def spender(db: Session, character: Character, feature_id: int) -> Spender | None:
    for uses in feature_uses(db, character):
        for feature in uses.spenders:
            if feature.id == feature_id:
                return Spender(uses, feature)
    return None


# --- Hit dice -----------------------------------------------------------------------------


@dataclass(frozen=True)
class HitDice:
    character_class: CharacterClass
    total: int  # one per class level
    spent: int

    @property
    def available(self) -> int:
        return max(0, self.total - self.spent)

    @property
    def die(self) -> int:
        return self.character_class.hit_die


def hit_dice(db: Session, character: Character) -> list[HitDice]:
    spent = {
        row.class_id: row.spent
        for row in db.scalars(
            select(CharacterHitDice).where(CharacterHitDice.character_id == character.id)
        )
    }
    return [
        HitDice(cc.character_class, cc.level, spent.get(cc.class_id, 0)) for cc in character.classes
    ]


# --- Slot recovery (Arcane Recovery) ------------------------------------------------------


def recovery_budget(uses: FeatureUses) -> int:
    """Total slot levels the feature can recover: half the class level, rounded up."""
    return math.ceil(uses.class_level / 2)


# --- Damage reactions ---------------------------------------------------------------------


@dataclass(frozen=True)
class DamageReaction:
    """A picked option the character can use in reaction to taking damage right now."""

    uses: FeatureUses
    option: ChoiceOption

    @property
    def kind(self) -> str:
        return self.option.damage_reaction["kind"]

    @property
    def dice(self) -> str:
        return self.option.damage_reaction["dice"]

    @property
    def die_count(self) -> int:
        return int(self.dice.split("d")[0])

    @property
    def die_sides(self) -> int:
        return int(self.dice.split("d")[1])


def damage_reactions(uses: list[FeatureUses]) -> list[DamageReaction]:
    """Damage reactions with a use left, offered before damage is applied."""
    return [
        DamageReaction(u, option)
        for u in uses
        if u.remaining > 0
        for option in u.options
        if option.damage_reaction
    ]


# --- Copying spells into the spellbook ----------------------------------------------------


@dataclass(frozen=True)
class CopyPanel:
    query: str = ""


def _copy_cost(spell: Spell) -> str:
    """2024 rules: 2 hours and 50 GP per spell level."""
    return f"{2 * spell.level} hours and {50 * spell.level} GP"


@dataclass(frozen=True)
class CopySearchView:
    query: str
    min_length: int
    results: list[tuple[Spell, str, list[str]]]  # spell, why it can't be copied, rule markers


def copy_search(db: Session, character: Character, query: str) -> CopySearchView:
    spells = search_copyable(db, query, character.user_id)
    known = always_prepared_reasons(db, character) | {
        str(entry.spell_id): "In your spellbook" for entry in spellbook(db, character.id)
    }
    return CopySearchView(
        query=query.strip(),
        min_length=COPY_SEARCH_MIN,
        results=[
            (spell, known.get(str(spell.id), ""), found)
            for spell, found in copy_warnings(db, character, spells).items()
        ],
    )


@dataclass(frozen=True)
class CopyConfirmView:
    spell: Spell
    query: str
    cost: str
    warnings: list[str]


def copy_confirmation(
    db: Session, character: Character, spell: Spell, query: str
) -> CopyConfirmView:
    return CopyConfirmView(
        spell=spell,
        query=query,
        cost=_copy_cost(spell),
        warnings=copy_warnings(db, character, [spell])[spell],
    )


def copyable(db: Session, key: str, user_id: int) -> Spell | None:
    return picked_row(db, Spell, _copyable_spells(user_id), key)


# --- The prepared editor ------------------------------------------------------------------


@dataclass(frozen=True)
class PreparedEditorView:
    character: Character
    options: list[OptionView]
    selected: list[str]
    known: dict[str, str]
    limit: int | None
    filter_schools: list[str]
    asking: str


def prepared_editor_view(
    db: Session, character: Character, selected: list[str] | None = None, asking: str = ""
) -> PreparedEditorView:
    book = spellbook(db, character.id)
    in_book = {str(e.spell_id) for e in book}
    if selected is None:
        prepared = prepared_spell_ids(db, character)
        selected = [str(e.spell_id) for e in book if e.spell_id in prepared]
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
        for entry in book
    ]
    return PreparedEditorView(
        character=character,
        options=options,
        selected=[key for key in selected if key in in_book],
        known=always_prepared_reasons(db, character),
        limit=prepared_limit(character),
        filter_schools=sorted({o.school for o in options}),
        asking=asking,
    )


def refreshed_prepared_editor_view(
    db: Session, character: Character, selected: list[str]
) -> PreparedEditorView:
    reload_all(db)
    return prepared_editor_view(db, character, selected)


# --- The Play sheet -----------------------------------------------------------------------


@dataclass(frozen=True)
class SheetView:
    """`read_only` is the shared view: the same sheet with every control left out, its links
    within `base_url` (/shared/<token>)."""

    user: User | None
    character: Character
    hp: HpView | None
    abilities: list[AbilityRow] | None
    attributes: Attributes
    skills: list[SkillRow] | None
    ac: ArmorClassView | None
    ac_spells: list[AcSpell]
    free_uses: dict[int, FeatureUses]  # rest-only ones (Arcane Recovery) are in the rest panel
    play_choices: list[PlayChoice]
    sheet_features: SheetFeatures
    castable: list[CastableSpell]
    slots: dict[int, SlotLevel]
    prepared_count: int
    prepared_limit: int | None
    has_spellbook: bool
    resting: bool  # the Short rest panel: hit dice and slot recovery stay off the main sheet
    items: list[CharacterItem]
    item_features: dict[int, list[Feature]]
    coin_summary: str
    inventory_digest: str
    healing_uses: list[HealingUse]
    ac_scrolls: list[CharacterItem]
    read_only: bool
    base_url: str
    share: CharacterShare | None
    pending_damage: int | None  # waiting on "use a reaction or take it all"
    spell_warnings: dict[int, list[str]]
    spell_notes: dict[int, str]
    copying: CopyPanel | None
    copy: CopySearchView | None
    reactions: list[tuple[DamageReaction, int]]  # with the ability modifier each roll adds
    hit_dice: list[HitDice]
    recoveries: list[tuple[FeatureUses, int]]


def sheet_view(
    db: Session,
    user: User | None,
    character: Character,
    *,
    resting: bool = False,
    pending_damage: int | None = None,
    copying: CopyPanel | None = None,
    read_only: bool = False,
    base_url: str | None = None,
) -> SheetView:
    # Every section needs the character's features; looking them up once keeps the sheet
    # within its query budget (tests/integration/test_sheet_queries.py).
    groups = feature_groups(db, character)
    uses = feature_uses(db, character, groups)
    choices = play_choices(db, character, groups)
    attrs = attributes(db, character, groups)
    castable = castable_spells(db, character, groups)
    slots = spell_slots(db, character)
    items = inventory(db, character)
    return SheetView(
        user=user,
        character=character,
        hp=hp_view(db, character),
        abilities=ability_rows(db, character, attrs),
        attributes=attrs,
        skills=skill_rows(db, character),
        ac=armor_class(db, character, groups),
        ac_spells=ac_spells(db, character, castable, slots),
        free_uses={u.feature.id: u for u in uses},
        play_choices=choices,
        sheet_features=sheet_features(db, character, groups, uses, choices),
        castable=castable,
        slots=slots,
        # Always-prepared spells don't count, even if also picked from the book before.
        prepared_count=len(
            prepared_spell_ids(db, character) - always_prepared_spells(db, character, groups).keys()
        ),
        prepared_limit=prepared_limit(character),
        has_spellbook=bool(spellbook(db, character.id)),
        resting=resting,
        items=items,
        item_features=item_features(db, items),
        coin_summary=coin_summary(coin_values(db, character)),
        inventory_digest=inventory_digest(db, character, items),
        healing_uses=healing_uses(items),
        ac_scrolls=ac_scrolls(items, active_ac_spell_ids(db, character)),
        read_only=read_only,
        base_url=base_url or f"/characters/{character.id}",
        share=None if read_only else public_share(db, character),
        pending_damage=pending_damage,
        spell_warnings=spell_warnings(db, character),
        spell_notes=spellbook_notes(db, character),
        copying=copying,
        copy=copy_search(db, character, copying.query) if copying else None,
        reactions=[
            (r, ability_modifier(db, character, r.option.damage_reaction.get("ability", "")))
            for r in damage_reactions(uses)
        ]
        if pending_damage is not None
        else [],
        hit_dice=hit_dice(db, character) if resting else [],
        recoveries=[(u, recovery_budget(u)) for u in uses if u.feature.slot_recovery is not None]
        if resting
        else [],
    )


def refreshed_sheet_view(
    db: Session,
    user: User,
    character: Character,
    *,
    resting: bool = False,
    pending_damage: int | None = None,
    copying: CopyPanel | None = None,
) -> SheetView:
    reload_all(db)
    return sheet_view(
        db, user, character, resting=resting, pending_damage=pending_damage, copying=copying
    )

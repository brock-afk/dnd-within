"""The custom item editor's form: what the player enters, and how it becomes an ItemDef whose
features carry the item's mechanics.

The form is flat, so it posts as plain fields; spell and ability rows are parallel lists
(spell_id[i], spell_cast[i], spell_note[i]). It's stored as the item's `definition` so the
editor can reopen it, and `build_item_def` derives the item from it:

  charges   -> feature "charges":  uses, plus the spells cast by spending a charge
  spells    -> feature "spells":   spells it keeps always prepared (cast with slots)
  bonuses   -> feature "benefits": grants (AC, darkvision, speed, resistances, saves, a tool)
  tool      -> feature "tool":     an in-play choice of any tool, changed on the Play sheet
  abilities -> one feature each:   text, with when it's used in front
"""

import re

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.content.models import Source
from app.content.schema import ItemDef
from app.inventory.rules import TOOLS
from app.spells.models import Spell

CATEGORIES = {"magic": "Magic item", "gear": "Gear", "consumable": "Consumable", "tool": "Tool"}
RARITIES = {
    "": "No rarity",
    "common": "Common",
    "uncommon": "Uncommon",
    "rare": "Rare",
    "very_rare": "Very rare",
    "legendary": "Legendary",
    "artifact": "Artifact",
}
RECHARGES = {"dawn": "At dawn", "long_rest": "On a long rest", "short_rest": "On a short rest"}
SPELL_CASTS = {"charge": "Spend a charge", "prepared": "Always prepared (uses spell slots)"}
TOOL_MODES = {"none": "None", "fixed": "A set tool", "choice": "Chosen on the Play sheet"}
ABILITIES = {"STR": "Strength", "DEX": "Dexterity", "CON": "Constitution",
             "INT": "Intelligence", "WIS": "Wisdom", "CHA": "Charisma"}
DAMAGE_TYPES = ["acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
                "piercing", "poison", "psychic", "radiant", "slashing", "thunder"]


class ItemForm(BaseModel):
    name: str = ""
    category: str = "magic"
    rarity: str = ""
    attunement: str = ""  # "1" when checked
    summary: str = ""
    description: str = ""
    charges: str = ""
    recharge: str = "dawn"
    regain: str = ""
    spell_id: list[str] = []
    spell_cast: list[str] = []
    spell_note: list[str] = []
    ac_bonus: str = ""
    darkvision: str = ""
    speed_bonus: str = ""
    resistances: list[str] = []
    saves: list[str] = []
    tool_mode: str = "none"
    tool: str = ""
    ability_name: list[str] = []
    ability_when: list[str] = []
    ability_text: list[str] = []
    # Not stored: the editor's own controls.
    add_row: str = ""  # "spell" or "ability": redraw with one more blank row
    remove_row: str = ""  # "spell:2": redraw without that row
    character: str = ""  # opened from this character's Add item: add it there once saved
    item_id: str = ""  # the item being edited, for redraws

    def spell_rows(self) -> list[tuple[str, str, str]]:
        n = max(len(self.spell_id), len(self.spell_cast), len(self.spell_note))
        pad = lambda values: values + [""] * (n - len(values))  # noqa: E731
        return list(zip(pad(self.spell_id), pad(self.spell_cast), pad(self.spell_note)))

    def ability_rows(self) -> list[tuple[str, str, str]]:
        n = max(len(self.ability_name), len(self.ability_when), len(self.ability_text))
        pad = lambda values: values + [""] * (n - len(values))  # noqa: E731
        return list(zip(pad(self.ability_name), pad(self.ability_when), pad(self.ability_text)))

    def set_spell_rows(self, rows) -> None:
        self.spell_id, self.spell_cast, self.spell_note = _columns(rows)

    def set_ability_rows(self, rows) -> None:
        self.ability_name, self.ability_when, self.ability_text = _columns(rows)

    def edit_rows(self) -> None:
        """Apply Add spell / Add ability / Remove from the editor's buttons."""
        kind, _, index = self.remove_row.partition(":")
        rows = {"spell": self.spell_rows(), "ability": self.ability_rows()}
        if kind in rows and index.isdigit() and int(index) < len(rows[kind]):
            del rows[kind][int(index)]
        if self.add_row == "spell":
            rows["spell"].append(("", "charge", ""))
        elif self.add_row == "ability":
            rows["ability"].append(("", "", ""))
        self.set_spell_rows(rows["spell"])
        self.set_ability_rows(rows["ability"])
        self.add_row = self.remove_row = ""

    def definition(self) -> dict:
        """What's stored to reopen the editor: the fields, without blank rows or controls."""
        self.set_spell_rows([r for r in self.spell_rows() if r[0]])
        self.set_ability_rows([r for r in self.ability_rows() if any(v.strip() for v in r)])
        return self.model_dump(exclude={"add_row", "remove_row", "character", "item_id"})


def _columns(rows: list[tuple[str, str, str]]) -> tuple[list[str], list[str], list[str]]:
    """Rows of three back into three parallel lists."""
    return tuple(list(column) for column in zip(*rows)) if rows else ([], [], [])


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50].strip("-") or "item"


def _number(raw: str, low: int, high: int, label: str, errors: dict, key: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    if not raw.isdigit() or not low <= int(raw) <= high:
        errors[key] = f"{label} is a whole number from {low} to {high}."
        return None
    return int(raw)


def _regain_text(form: ItemForm) -> str:
    if form.recharge == "dawn":
        return f"regains {form.regain.strip()} at dawn" if form.regain.strip() else "all regained at dawn"
    return "regained on a short or long rest" if form.recharge == "short_rest" else "regained on a long rest"


def build_item_def(db: Session, form: ItemForm) -> tuple[ItemDef | None, dict[str, str]]:
    """The item the form describes, or (None, {field: problem})."""
    errors: dict[str, str] = {}
    name = form.name.strip()
    if not name or len(name) > 80:
        errors["name"] = "Give the item a name (up to 80 characters)."
    summary = form.summary.strip()
    if not summary or len(summary) > 255:
        errors["summary"] = "Describe it in a sentence (up to 255 characters); it's shown in lists."
    if form.category not in CATEGORIES:
        errors["category"] = "Choose a type."
    if form.rarity not in RARITIES:
        errors["rarity"] = "Choose a rarity."
    charges = _number(form.charges, 1, 99, "Charges", errors, "charges")
    if form.recharge not in RECHARGES:
        errors["charges"] = "Choose when charges come back."
    if form.regain.strip() and form.recharge != "dawn":
        errors["regain"] = "A number regained is only for charges that come back at dawn."

    # Spells: each one cast with a charge, or kept always prepared.
    charge_spells, prepared_spells = [], []
    for spell_key, cast, note in form.spell_rows():
        if not spell_key:
            continue
        spell = db.get(Spell, int(spell_key)) if spell_key.isdigit() else None
        if spell is None or cast not in SPELL_CASTS:
            errors["spells"] = "Choose a spell from the list for each row."
            continue
        if len(note.strip()) > 255:
            errors["spells"] = "Spell notes are up to 255 characters."
        ref = f"{db.get(Source, spell.source_id).slug}/{spell.slug}"
        entry = {"spell": ref, "note": note.strip() or None}
        (charge_spells if cast == "charge" else prepared_spells).append((spell, entry))
    if charge_spells and charges is None:
        errors["spells"] = "Spells cast with a charge need the item to have charges."

    # Always-on benefits while attuned (or carried).
    grants: dict = {}
    if (ac := _number(form.ac_bonus, 1, 10, "AC bonus", errors, "ac_bonus")) is not None:
        grants["ac_bonus"] = ac
    if (dv := _number(form.darkvision, 5, 300, "Darkvision", errors, "darkvision")) is not None:
        grants["darkvision"] = dv
    if (sp := _number(form.speed_bonus, 5, 120, "Speed bonus", errors, "speed_bonus")) is not None:
        grants["speed_bonus"] = sp
    if resistances := [r for r in form.resistances if r in DAMAGE_TYPES]:
        grants["resistances"] = resistances
    if saves := [a for a in form.saves if a in ABILITIES]:
        grants["save_proficiencies"] = saves
    if form.tool_mode not in TOOL_MODES:
        errors["tool"] = "Choose how the tool proficiency works."
    elif form.tool_mode == "fixed":
        if form.tool not in TOOLS:
            errors["tool"] = "Choose the tool."
        else:
            grants["tool_proficiencies"] = [form.tool]

    abilities = []
    for i, (ability, when, text) in enumerate(form.ability_rows()):
        ability, when, text = ability.strip(), when.strip(), text.strip()
        if not (ability or when or text):
            continue
        line = f"{when}: {text}" if when else text
        if not ability or not text or len(ability) > 80 or len(line) > 500:
            errors["abilities"] = (
                "Each ability needs a name (up to 80 characters) and what it does (up to 500 "
                "with its timing)."
            )
            continue
        abilities.append({"slug": f"ability-{i + 1}", "name": ability, "summary": line})

    if errors:
        return None, errors

    features = []
    if charges is not None:
        spend = ", ".join(s.name for s, _ in charge_spells)
        features.append({
            "slug": "charges",
            "name": f"{name} charges"[:80],
            "summary": f"{charges} charges, {_regain_text(form)}."
            + (f" Spend one to cast {spend} without a spell slot." if spend else ""),
            "uses": {
                "max": charges,
                "recharge": form.recharge,
                **({"regain": form.regain.strip()} if form.regain.strip() else {}),
            },
            "spells": [{**entry, "free_cast": True} for _, entry in charge_spells],
        })
    if prepared_spells:
        features.append({
            "slug": "spells",
            "name": "Spells",
            "summary": "Always prepared: " + ", ".join(s.name for s, _ in prepared_spells) + ".",
            "spells": [entry for _, entry in prepared_spells],
        })
    if grants:
        features.append({
            "slug": "benefits",
            "name": "While attuned" if form.attunement else "While carried",
            "summary": _benefits_text(grants),
            "grants": grants,
        })
    if form.tool_mode == "choice":
        features.append({
            "slug": "tool",
            "name": "Tool proficiency",
            "summary": "Proficiency with one tool of your choice; change it on the Play sheet.",
            "choices": [{
                "slug": "tool",
                "name": "Tool",
                "kind": "option",
                "in_play": True,
                "options": [
                    {"slug": slugify(tool), "name": tool, "summary": f"Proficiency with {tool}.",
                     "grants": {"tool_proficiencies": [tool]}}
                    for tool in TOOLS
                ],
            }],
        })
    features.extend(abilities)

    data = {
        "slug": slugify(name),
        "name": name,
        "category": form.category,
        "rarity": form.rarity or None,
        "summary": summary,
        "description": form.description.strip() or None,
        "requires_attunement": bool(form.attunement),
        "features": features,
    }
    try:
        return ItemDef.model_validate(data), {}
    except ValidationError as exc:
        messages = sorted({err["msg"].removeprefix("Value error, ") for err in exc.errors()})
        return None, {"_form": " ".join(messages)}


def _benefits_text(grants: dict) -> str:
    parts = []
    if grants.get("ac_bonus"):
        parts.append(f"+{grants['ac_bonus']} AC")
    if grants.get("darkvision"):
        parts.append(f"Darkvision {grants['darkvision']} ft")
    if grants.get("speed_bonus"):
        parts.append(f"+{grants['speed_bonus']} ft speed")
    if grants.get("resistances"):
        parts.append("Resistance to " + ", ".join(grants["resistances"]) + " damage")
    if grants.get("save_proficiencies"):
        parts.append(
            "Proficiency in " + ", ".join(ABILITIES[a] for a in grants["save_proficiencies"])
            + " saving throws"
        )
    if grants.get("tool_proficiencies"):
        parts.append("Proficiency with " + ", ".join(grants["tool_proficiencies"]))
    return "; ".join(parts) + "."

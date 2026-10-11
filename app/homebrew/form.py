"""The custom item editor's form: what the player enters, and how it becomes an ItemDef whose
features carry the item's mechanics.

The form is flat, so it posts as plain fields; spell and ability rows are parallel lists
(spell_id[i], spell_charges[i], ...). It's stored as the item's `definition` so the editor can
reopen it, and `build_item_def` derives the item from it:

  charges   -> feature "charges":  uses, plus the spells cast by spending charges
  spells    -> feature "spells":   spells kept always prepared without a charge cost
  bonuses   -> feature "benefits": grants (AC, darkvision, speed, resistances, saves, a tool)
  tool      -> feature "tool":     an in-play choice of any tool, changed on the Play sheet
  abilities -> one feature each:   its action, and the charges a use spends (Use on the sheet)
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
PREPARED = {"no": "No: charges only", "yes": "Yes: also cast with spell slots"}
ACTIONS = {"": "None", "action": "Action", "bonus_action": "Bonus Action", "reaction": "Reaction"}
TOOL_MODES = {"none": "None", "fixed": "A set tool", "choice": "Chosen on the Play sheet"}
ABILITIES = {
    "STR": "Strength",
    "DEX": "Dexterity",
    "CON": "Constitution",
    "INT": "Intelligence",
    "WIS": "Wisdom",
    "CHA": "Charisma",
}
DAMAGE_TYPES = [
    "acid",
    "bludgeoning",
    "cold",
    "fire",
    "force",
    "lightning",
    "necrotic",
    "piercing",
    "poison",
    "psychic",
    "radiant",
    "slashing",
    "thunder",
]

SPELL_FIELDS = ["spell_id", "spell_charges", "spell_prepared", "spell_note"]
ABILITY_FIELDS = ["ability_name", "ability_action", "ability_charges", "ability_text"]


class ItemForm(BaseModel):
    name: str = ""
    category: str = "magic"
    rarity: str = ""
    attunement: str = ""  # "1" when checked
    summary: str = ""
    description: str = ""
    healing: str = ""  # dice healed when used ("2d4+2"): drunk from the HP panel
    charges: str = ""
    recharge: str = "dawn"
    regain: str = ""
    spell_id: list[str] = []
    spell_charges: list[str] = []  # charges a cast spends; blank: not cast with charges
    spell_prepared: list[str] = []  # "yes": also always prepared, cast with slots
    spell_note: list[str] = []
    ac_bonus: str = ""
    darkvision: str = ""
    speed_bonus: str = ""
    resistances: list[str] = []
    saves: list[str] = []
    tool_mode: str = "none"
    tool: str = ""
    ability_name: list[str] = []
    ability_action: list[str] = []  # "", "action", "bonus_action", "reaction"
    ability_charges: list[str] = []  # charges a use spends; blank: none
    ability_text: list[str] = []
    # Items saved before these fields existed; converted by `upgrade` when reopened.
    spell_cast: list[str] = []
    ability_when: list[str] = []
    # Not stored: the editor's own controls.
    add_row: str = ""  # "spell" or "ability": redraw with one more blank row
    remove_row: str = ""  # "spell:2": redraw without that row
    character: str = ""  # opened from this character's Add item: add it there once saved
    item_id: str = ""  # the item being edited, for redraws

    def _rows(self, fields: list[str]) -> list[list[str]]:
        columns = [getattr(self, f) for f in fields]
        n = max(len(c) for c in columns)
        return [[c[i] if i < len(c) else "" for c in columns] for i in range(n)]

    def _set_rows(self, fields: list[str], rows: list[list[str]]) -> None:
        for i, field in enumerate(fields):
            setattr(self, field, [row[i] for row in rows])

    def spell_rows(self) -> list[list[str]]:
        """[spell id, charges, prepared, note] per row."""
        return self._rows(SPELL_FIELDS)

    def ability_rows(self) -> list[list[str]]:
        """[name, action, charges, text] per row."""
        return self._rows(ABILITY_FIELDS)

    def upgrade(self) -> ItemForm:
        """Convert an item saved by the first version of the editor: a spell's "Spend a charge"
        or "Always prepared", and an ability's free-text "Bonus Action · 1 charge"."""
        if self.spell_cast and not self.spell_charges:
            self.spell_charges = ["1" if cast == "charge" else "" for cast in self.spell_cast]
            self.spell_prepared = ["no" if cast == "charge" else "yes" for cast in self.spell_cast]
        if self.ability_when and not self.ability_action:
            self.ability_action, self.ability_charges = [], []
            for when in self.ability_when:
                text = when.lower()
                action = (
                    "bonus_action"
                    if "bonus" in text
                    else "reaction"
                    if "reaction" in text
                    else "action"
                    if "action" in text
                    else ""
                )
                count = re.search(r"(\d+)\s*charge", text)
                self.ability_action.append(action)
                self.ability_charges.append(count[1] if count else "1" if "charge" in text else "")
        self.spell_cast, self.ability_when = [], []
        return self

    def edit_rows(self) -> None:
        """Apply Add spell / Add ability / Remove from the editor's buttons."""
        kind, _, index = self.remove_row.partition(":")
        rows = {"spell": self.spell_rows(), "ability": self.ability_rows()}
        if kind in rows and index.isdigit() and int(index) < len(rows[kind]):
            del rows[kind][int(index)]
        if self.add_row == "spell":
            rows["spell"].append(["", "1", "no", ""])
        elif self.add_row == "ability":
            rows["ability"].append(["", "", "", ""])
        self._set_rows(SPELL_FIELDS, rows["spell"])
        self._set_rows(ABILITY_FIELDS, rows["ability"])
        self.add_row = self.remove_row = ""

    def definition(self) -> dict:
        """What's stored to reopen the editor: the fields, without blank rows or controls."""
        self._set_rows(SPELL_FIELDS, [r for r in self.spell_rows() if r[0]])
        self._set_rows(
            ABILITY_FIELDS, [r for r in self.ability_rows() if r[0].strip() or r[3].strip()]
        )
        return self.model_dump(
            exclude={"add_row", "remove_row", "character", "item_id", "spell_cast", "ability_when"}
        )


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
        return (
            f"regains {form.regain.strip()} at dawn"
            if form.regain.strip()
            else "all regained at dawn"
        )
    return (
        "regained on a short or long rest"
        if form.recharge == "short_rest"
        else "regained on a long rest"
    )


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
    if form.healing.strip() and not re.fullmatch(
        r"\s*\d+d\d+(\s*[+-]\s*\d+)?\s*|\s*\d+\s*", form.healing
    ):
        errors["healing"] = "Healing is dice like 2d4+2, or a number."
    charges = _number(form.charges, 1, 99, "Charges", errors, "charges")
    if form.recharge not in RECHARGES:
        errors["charges"] = "Choose when charges come back."
    if form.regain.strip() and form.recharge != "dawn":
        errors["regain"] = "A number regained is only for charges that come back at dawn."

    # Spells: cast by spending charges, and/or kept always prepared (cast with slots).
    charge_spells, prepared_spells = [], []
    for spell_key, spell_charges, prepared, note in form.spell_rows():
        if not spell_key:
            continue
        spell = db.get(Spell, int(spell_key)) if spell_key.isdigit() else None
        if spell is None:
            errors["spells"] = "Choose a spell from the list for each row."
            continue
        cost = _number(spell_charges, 1, 20, "A spell's charges", errors, "spells")
        if cost is None and prepared != "yes" and "spells" not in errors:
            errors["spells"] = (
                "Each spell needs a charge cost, or to be always prepared (cast with slots)."
            )
        if len(note.strip()) > 255:
            errors["spells"] = "Spell notes are up to 255 characters."
        ref = f"{db.get(Source, spell.source_id).slug}/{spell.slug}"
        entry = {"spell": ref, "note": note.strip() or None}
        if cost is not None:
            charge_spells.append(
                (
                    spell,
                    {
                        **entry,
                        "free_cast": True,
                        "charges": cost,
                        "always_prepared": prepared == "yes",
                    },
                )
            )
        elif prepared == "yes":
            prepared_spells.append((spell, entry))
    if charge_spells and charges is None:
        errors["spells"] = "Spells cast with charges need the item to have charges."

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

    # Abilities: what each takes (an action, bonus action, reaction) and the charges it spends.
    abilities = []
    for i, (ability, action, ability_charges, text) in enumerate(form.ability_rows()):
        ability, text = ability.strip(), text.strip()
        if not (ability or text):
            continue
        if not ability or not text or len(ability) > 80 or len(text) > 500:
            errors["abilities"] = (
                "Each ability needs a name (up to 80 characters) and what it does (up to 500)."
            )
            continue
        if action not in ACTIONS:
            errors["abilities"] = "Choose what each ability takes to use."
            continue
        cost = _number(ability_charges, 1, 20, "An ability's charges", errors, "abilities")
        if cost is not None and charges is None:
            errors["abilities"] = "Abilities that spend charges need the item to have charges."
        abilities.append(
            {
                "slug": f"ability-{i + 1}",
                "name": ability,
                "summary": text,
                "action": action or None,
                **({"spends": {"feature": "charges", "amount": cost}} if cost is not None else {}),
            }
        )

    if errors:
        return None, errors

    features = []
    if charges is not None:
        uses = [
            f"cast {spell.name} ({_charges(entry['charges'])})" for spell, entry in charge_spells
        ] + [f"{a['name']} ({_charges(a['spends']['amount'])})" for a in abilities if "spends" in a]
        features.append(
            {
                "slug": "charges",
                "name": f"{name} charges"[:80],
                "summary": f"{charges} charges, {_regain_text(form)}."
                + (f" Spend them to {', '.join(uses)}." if uses else ""),
                "uses": {
                    "max": charges,
                    "recharge": form.recharge,
                    **({"regain": form.regain.strip()} if form.regain.strip() else {}),
                },
                "spells": [entry for _, entry in charge_spells],
            }
        )
    if prepared_spells:
        features.append(
            {
                "slug": "spells",
                "name": "Spells",
                "summary": "Always prepared: "
                + ", ".join(s.name for s, _ in prepared_spells)
                + ".",
                "spells": [entry for _, entry in prepared_spells],
            }
        )
    if grants:
        features.append(
            {
                "slug": "benefits",
                "name": "While attuned" if form.attunement else "While carried",
                "summary": _benefits_text(grants),
                "grants": grants,
            }
        )
    if form.tool_mode == "choice":
        features.append(
            {
                "slug": "tool",
                "name": "Tool proficiency",
                "summary": "Proficiency with one tool of your choice; change it on the Play sheet.",
                "choices": [
                    {
                        "slug": "tool",
                        "name": "Tool",
                        "kind": "option",
                        "in_play": True,
                        "options": [
                            {
                                "slug": slugify(tool),
                                "name": tool,
                                "summary": f"Proficiency with {tool}.",
                                "grants": {"tool_proficiencies": [tool]},
                            }
                            for tool in TOOLS
                        ],
                    }
                ],
            }
        )
    features.extend(abilities)

    data = {
        "slug": slugify(name),
        "name": name,
        "category": form.category,
        "rarity": form.rarity or None,
        "summary": summary,
        "description": form.description.strip() or None,
        "healing": form.healing.strip() or None,
        "requires_attunement": bool(form.attunement),
        "features": features,
    }
    try:
        return ItemDef.model_validate(data), {}
    except ValidationError as exc:
        messages = sorted({err["msg"].removeprefix("Value error, ") for err in exc.errors()})
        return None, {"_form": " ".join(messages)}


def _charges(n: int) -> str:
    return f"{n} charge{'s' if n != 1 else ''}"


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
            "Proficiency in "
            + ", ".join(ABILITIES[a] for a in grants["save_proficiencies"])
            + " saving throws"
        )
    if grants.get("tool_proficiencies"):
        parts.append("Proficiency with " + ", ".join(grants["tool_proficiencies"]))
    return "; ".join(parts) + "."

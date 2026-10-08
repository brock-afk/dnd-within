"""Classes from the 2024 Player's Handbook. Synced into the `classes` table on startup."""

from app.features.schema import ChoiceDef, FeatureDef

CLASSES = [
    {"slug": "barbarian", "name": "Barbarian", "summary": "A fierce warrior fueled by primal rage.", "hit_die": 12},
    {"slug": "bard", "name": "Bard", "summary": "A performer whose music and words weave magic.", "hit_die": 8},
    {"slug": "cleric", "name": "Cleric", "summary": "A priestly champion wielding divine magic.", "hit_die": 8},
    {"slug": "druid", "name": "Druid", "summary": "A keeper of nature who shapeshifts and calls on the wild.", "hit_die": 8},
    {"slug": "fighter", "name": "Fighter", "summary": "A master of weapons, armor, and battlefield tactics.", "hit_die": 10},
    {"slug": "monk", "name": "Monk", "summary": "A martial artist who channels inner focus.", "hit_die": 8},
    {"slug": "paladin", "name": "Paladin", "summary": "A holy warrior bound by a sacred oath.", "hit_die": 10},
    {"slug": "ranger", "name": "Ranger", "summary": "A wilderness hunter blending skill and nature magic.", "hit_die": 10},
    {"slug": "rogue", "name": "Rogue", "summary": "A stealthy expert who strikes where it hurts.", "hit_die": 8},
    {"slug": "sorcerer", "name": "Sorcerer", "summary": "A caster with raw magic in their blood.", "hit_die": 6},
    {"slug": "warlock", "name": "Warlock", "summary": "A caster empowered by a pact with an otherworldly patron.", "hit_die": 8},
    {"slug": "wizard", "name": "Wizard", "summary": "A scholar who masters magic through study.", "hit_die": 6},
]

# Features per class. Only Wizard so far; the others show "not available yet".
CLASS_FEATURES: dict[str, list[FeatureDef]] = {
    "wizard": [
        FeatureDef(
            slug="proficiencies",
            name="Proficiencies",
            applies_to="starting_class",
            summary="Hit die d6. Saving throws: Intelligence, Wisdom. Weapons: Simple. Armor: none.",
            choices=[
                ChoiceDef(
                    slug="skills",
                    name="Skill Proficiencies",
                    kind="skill",
                    count=2,
                    criteria={"from": ["arcana", "history", "insight", "investigation",
                                       "medicine", "nature", "religion"]},
                )
            ],
        ),
        FeatureDef(
            slug="spellcasting",
            name="Spellcasting",
            summary="You cast wizard spells with Intelligence, learned from your spellbook.",
            choices=[
                ChoiceDef(slug="cantrips", name="Cantrips", kind="spell", count=3,
                          criteria={"class": "wizard", "level": 0}),
                ChoiceDef(slug="spellbook", name="Spellbook", kind="spell", count=6,
                          criteria={"class": "wizard", "level": 1}),
            ],
        ),
        FeatureDef(
            slug="ritual-adept",
            name="Ritual Adept",
            summary="Cast any Ritual spell in your spellbook as a ritual, even if it isn't prepared.",
        ),
        FeatureDef(
            slug="subclass",
            name="Wizard Subclass",
            level=3,
            summary="Specialize in a school of magic.",
            choices=[ChoiceDef(slug="subclass", name="Wizard Subclass", kind="subclass")],
        ),
        FeatureDef(
            slug="arcane-recovery",
            name="Arcane Recovery",
            summary="After a Short Rest, regain spell slots totaling up to half your wizard level "
            "(rounded up), none of level 6+. Once per Long Rest.",
        ),
    ],
}

# Subclasses per class slug. Synced into the `subclasses` table on startup.
SUBCLASSES: dict[str, list[dict]] = {
    "wizard": [
        {"slug": "abjurer", "name": "Abjurer", "summary": "Shields allies and shuts down hostile magic."},
        {"slug": "diviner", "name": "Diviner", "summary": "Glimpses the future and bends fate."},
        {"slug": "evoker", "name": "Evoker", "summary": "Wields raw, destructive elemental magic."},
        {"slug": "illusionist", "name": "Illusionist", "summary": "Weaves sights and sounds that fool the senses."},
    ],
}


def _savant(school: str) -> FeatureDef:
    return FeatureDef(
        slug="savant",
        name=f"{school} Savant",
        level=3,
        summary=f"Add two {school} spells of level 2 or lower to your spellbook for free, and one "
        "more whenever you gain access to a new level of spell slots. (Picking them arrives "
        "with the spellbook update.)",
    )


# Subclass features keyed by (class slug, subclass slug). Level 3 only so far.
SUBCLASS_FEATURES: dict[tuple[str, str], list[FeatureDef]] = {
    ("wizard", "abjurer"): [
        _savant("Abjuration"),
        FeatureDef(
            slug="arcane-ward",
            name="Arcane Ward",
            level=3,
            summary="Casting an Abjuration spell with a slot can create a ward that absorbs damage "
            "for you: 2 × Wizard level + INT modifier HP. Abjuration spells, or spending a slot as "
            "a Bonus Action, recharge it.",
        ),
    ],
    ("wizard", "diviner"): [
        _savant("Divination"),
        FeatureDef(
            slug="portent",
            name="Portent",
            level=3,
            summary="After a Long Rest, roll two d20s. Use each once to replace an attack roll, "
            "saving throw, or ability check made by you or a creature you can see.",
        ),
    ],
    ("wizard", "evoker"): [
        _savant("Evocation"),
        FeatureDef(
            slug="potent-cantrip",
            name="Potent Cantrip",
            level=3,
            summary="When your damaging cantrip misses or the target succeeds on its save, it still "
            "takes half the damage (but no other effects).",
        ),
    ],
    ("wizard", "illusionist"): [
        _savant("Illusion"),
        FeatureDef(
            slug="improved-illusions",
            name="Improved Illusions",
            level=3,
            summary="Cast Illusion spells without Verbal components, with +60 ft range when it's 10 ft "
            "or more. You know Minor Illusion (or another cantrip if you already do), can make sound "
            "and image together, and can cast it as a Bonus Action.",
        ),
    ],
}

"""Classes from the 2024 Player's Handbook. Synced into the `classes` table on startup."""

from app.features.schema import ChoiceDef, FeatureDef

CLASSES = [
    {"slug": "barbarian", "name": "Barbarian", "summary": "A fierce warrior fueled by primal rage."},
    {"slug": "bard", "name": "Bard", "summary": "A performer whose music and words weave magic."},
    {"slug": "cleric", "name": "Cleric", "summary": "A priestly champion wielding divine magic."},
    {"slug": "druid", "name": "Druid", "summary": "A keeper of nature who shapeshifts and calls on the wild."},
    {"slug": "fighter", "name": "Fighter", "summary": "A master of weapons, armor, and battlefield tactics."},
    {"slug": "monk", "name": "Monk", "summary": "A martial artist who channels inner focus."},
    {"slug": "paladin", "name": "Paladin", "summary": "A holy warrior bound by a sacred oath."},
    {"slug": "ranger", "name": "Ranger", "summary": "A wilderness hunter blending skill and nature magic."},
    {"slug": "rogue", "name": "Rogue", "summary": "A stealthy expert who strikes where it hurts."},
    {"slug": "sorcerer", "name": "Sorcerer", "summary": "A caster with raw magic in their blood."},
    {"slug": "warlock", "name": "Warlock", "summary": "A caster empowered by a pact with an otherworldly patron."},
    {"slug": "wizard", "name": "Wizard", "summary": "A scholar who masters magic through study."},
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
            slug="arcane-recovery",
            name="Arcane Recovery",
            summary="After a Short Rest, regain spell slots totaling up to half your wizard level "
            "(rounded up), none of level 6+. Once per Long Rest.",
        ),
    ],
}

"""Species from the 2024 Player's Handbook. Synced into the `species` table on startup."""

from app.features.schema import ChoiceDef, FeatureDef, OptionDef

SPECIES = [
    {"slug": "aasimar", "name": "Aasimar", "summary": "Mortals touched by celestial power, able to heal and shine."},
    {"slug": "dragonborn", "name": "Dragonborn", "summary": "Draconic folk with a breath weapon and elemental resistance."},
    {"slug": "dwarf", "name": "Dwarf", "summary": "Hardy, stone-attuned folk with darkvision and grit."},
    {"slug": "elf", "name": "Elf", "summary": "Long-lived, keen-sensed folk of fey ancestry."},
    {"slug": "gnome", "name": "Gnome", "summary": "Small, clever folk with a knack for magic."},
    {"slug": "goliath", "name": "Goliath", "summary": "Towering folk with the gifts of giant ancestors."},
    {"slug": "halfling", "name": "Halfling", "summary": "Small, brave folk blessed with uncanny luck."},
    {"slug": "human", "name": "Human", "summary": "Adaptable and ambitious, skilled in many things."},
    {"slug": "orc", "name": "Orc", "summary": "Enduring folk who push through when others fall."},
    {"slug": "tiefling", "name": "Tiefling", "summary": "Folk with a fiendish legacy and innate magic."},
]

# Traits per species. Only Goliath so far; the others show "not available yet".
SPECIES_FEATURES: dict[str, list[FeatureDef]] = {
    "goliath": [
        FeatureDef(slug="size-speed", name="Size and Speed", summary="Medium. Speed 35 ft."),
        FeatureDef(
            slug="giant-ancestry",
            name="Giant Ancestry",
            summary="A boon from your giant ancestors. Uses equal your Proficiency Bonus, "
            "regained on a Long Rest.",
            choices=[
                ChoiceDef(
                    slug="giant-ancestry",
                    name="Giant Ancestry",
                    kind="option",
                    options=[
                        OptionDef(slug="cloud", name="Cloud's Jaunt (Cloud Giant)",
                                  summary="Bonus Action: teleport up to 30 ft to a space you can see."),
                        OptionDef(slug="fire", name="Fire's Burn (Fire Giant)",
                                  summary="When you hit with an attack, deal an extra 1d10 fire."),
                        OptionDef(slug="frost", name="Frost's Chill (Frost Giant)",
                                  summary="When you hit, deal an extra 1d6 cold and cut the "
                                  "target's speed by 10 ft until your next turn."),
                        OptionDef(slug="hill", name="Hill's Tumble (Hill Giant)",
                                  summary="When you hit a Large or smaller creature, knock it Prone."),
                        OptionDef(slug="stone", name="Stone's Endurance (Stone Giant)",
                                  summary="Reaction when you take damage: roll 1d12 + Con "
                                  "modifier and reduce the damage by that much."),
                        OptionDef(slug="storm", name="Storm's Thunder (Storm Giant)",
                                  summary="Reaction when a creature within 60 ft damages you: "
                                  "deal 1d8 thunder to it."),
                    ],
                )
            ],
        ),
        FeatureDef(
            slug="large-form",
            name="Large Form",
            level=5,
            summary="Bonus Action: become Large for 10 minutes, with advantage on Strength "
            "checks and +10 ft speed. Once per Long Rest.",
        ),
        FeatureDef(
            slug="powerful-build",
            name="Powerful Build",
            summary="Advantage on checks to end the Grappled condition, and you count as one "
            "size larger for carrying capacity.",
        ),
    ],
}

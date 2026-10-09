"""Choice kinds: where a choice's options come from and where a character's picks are saved.

Most kinds work the same way: options are rows of some `target` table, and each pick is a
row in a `pick` table holding (character_id, choice_id, <target>_id). The subclass kind is
the exception: its pick is stored on the character's class row. Adding a new kind of choice
(languages, tools, feats, ...) means adding a subclass here and to KINDS.
"""

from dataclasses import dataclass

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.classes.models import CharacterClass, CharacterClassLevel, Subclass
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature
from app.skills.models import CharacterSkill, Skill
from app.spells.models import CharacterSpell, Spell, SpellbookEntry


@dataclass(frozen=True)
class OptionView:
    slug: str
    name: str
    summary: str = ""
    detail: str = ""
    group: str = ""  # options with groups are shown in collapsible sections, e.g. spell levels
    school: str = ""  # spells only: enables the school/ritual/name filters
    ritual: bool = False
    warnings: tuple[str, ...] = ()  # rule markers, e.g. "Not on the Wizard list"
    note: str = ""  # e.g. "Copied to spellbook · scroll from the crypt"


class ChoiceKind:
    target: type  # table the options come from
    pick: type  # table a character's picks are saved in
    target_fk: str  # column on `pick` pointing at `target`
    # Shown on options the character already has from somewhere else (they can't be picked).
    known_label = "Already known"
    noun = ("option", "options")  # for counts like "31 spells"

    def pick_values(self) -> dict:
        """Extra columns to set on each new pick row."""
        return {}

    def options_query(self, choice: Choice) -> Select:
        raise NotImplementedError

    def view(self, obj) -> OptionView:
        raise NotImplementedError

    def options(self, db: Session, choice: Choice) -> list[OptionView]:
        return [self.view(obj) for obj in db.scalars(self.options_query(choice))]

    def picked(self, db: Session, choice: Choice, character_id: int) -> list[OptionView]:
        fk = getattr(self.pick, self.target_fk)
        query = (
            select(self.target)
            .join(self.pick, fk == self.target.id)
            .where(self.pick.character_id == character_id, self.pick.choice_id == choice.id)
            .order_by(self.target.name)
        )
        return [self.view(obj) for obj in db.scalars(query)]

    def save(self, db: Session, choice: Choice, character_id: int, slugs: list[str]) -> str | None:
        """Replace this choice's picks. Returns an error message instead if they aren't valid."""
        targets = db.scalars(self.options_query(choice).where(self.target.slug.in_(slugs))).all()
        if len(targets) != len(slugs):
            return "That isn't one of the options."

        fk = getattr(self.pick, self.target_fk)
        already_have = db.scalars(
            select(self.target.name)
            .join(self.pick, fk == self.target.id)
            .where(
                self.pick.character_id == character_id,
                fk.in_([t.id for t in targets]),
                self.pick.choice_id.is_distinct_from(choice.id),
            )
        ).all()
        if already_have:
            return f"You already have {', '.join(already_have)} from another feature."

        db.execute(
            delete(self.pick).where(
                self.pick.character_id == character_id, self.pick.choice_id == choice.id
            )
        )
        db.add_all(
            self.pick(
                character_id=character_id,
                choice_id=choice.id,
                **{self.target_fk: t.id},
                **self.pick_values(),
            )
            for t in targets
        )
        db.commit()
        return None

    def already_have(self, db: Session, choice: Choice, character_id: int) -> set[str]:
        """Slugs of options the character has from anything other than this choice."""
        fk = getattr(self.pick, self.target_fk)
        query = (
            select(self.target.slug)
            .join(self.pick, fk == self.target.id)
            .where(
                self.pick.character_id == character_id,
                self.pick.choice_id.is_distinct_from(choice.id),
            )
        )
        return set(db.scalars(query))

    def picked_choice_ids(self, db: Session, character_id: int) -> set[int]:
        """Every choice of this kind the character has picks for."""
        query = select(self.pick.choice_id).where(self.pick.character_id == character_id)
        return {cid for cid in db.scalars(query) if cid is not None}

    def clear(self, db: Session, choice_ids: list[int], character_id: int) -> None:
        """Remove the character's picks for these choices. Doesn't commit."""
        db.execute(
            delete(self.pick).where(
                self.pick.character_id == character_id, self.pick.choice_id.in_(choice_ids)
            )
        )


class OptionKind(ChoiceKind):
    """Options listed on the choice itself (choice_options), e.g. Giant Ancestry."""

    target, pick, target_fk = ChoiceOption, CharacterChoicePick, "option_id"

    def options_query(self, choice):
        return (
            select(ChoiceOption)
            .where(ChoiceOption.choice_id == choice.id)
            .order_by(ChoiceOption.position)
        )

    def view(self, option):
        return OptionView(option.slug, option.name, option.summary)


class SkillKind(ChoiceKind):
    """Skill proficiencies. criteria: {"skill_ids": [...]}, resolved from slugs on import."""

    target, pick, target_fk = Skill, CharacterSkill, "skill_id"
    known_label = "Already proficient"

    def options_query(self, choice):
        return (
            select(Skill).where(Skill.id.in_(choice.criteria["skill_ids"])).order_by(Skill.name)
        )

    def view(self, skill):
        return OptionView(skill.slug, skill.name, detail=skill.ability)


class SpellKind(ChoiceKind):
    """Spells known from a class's list, like cantrips. criteria: {"class_id": ...} plus either
    "level" (an exact spell level) or "max_level" (levels 1 up to it). The class is resolved
    from its slug on import."""

    target, pick, target_fk = Spell, CharacterSpell, "spell_id"
    noun = ("spell", "spells")

    def options_query(self, choice):
        criteria = choice.criteria
        query = select(Spell).join(Spell.classes).where(CharacterClass.id == criteria["class_id"])
        if "level" in criteria:
            query = query.where(Spell.level == criteria["level"])
        else:
            query = query.where(Spell.level.between(1, criteria["max_level"]))
        return query.order_by(Spell.level, Spell.name)

    def view(self, spell):
        group = "Cantrips" if spell.level == 0 else f"Level {spell.level}"
        return OptionView(
            spell.slug, spell.name, spell.summary, spell.detail, group, spell.school, spell.ritual
        )


class SpellbookKind(SpellKind):
    """Spells written into a Wizard's spellbook on level up. Same options as SpellKind, but
    picks become spellbook entries."""

    pick = SpellbookEntry
    known_label = "In your spellbook"

    def pick_values(self):
        return {"acquired_via": "level_up"}


class SubclassKind(ChoiceKind):
    """A class's subclass. The pick is stored on the character's row for that class
    (character_classes.subclass_id), so each class has its own subclass."""

    target = Subclass

    def options_query(self, choice):
        return (
            select(Subclass)
            .where(Subclass.class_id == choice.feature.class_id)
            .order_by(Subclass.name)
        )

    def view(self, subclass):
        return OptionView(subclass.slug, subclass.name, subclass.summary)

    def _class_row(self, db, class_id, character_id) -> CharacterClassLevel | None:
        return db.scalar(
            select(CharacterClassLevel).where(
                CharacterClassLevel.character_id == character_id,
                CharacterClassLevel.class_id == class_id,
            )
        )

    def picked(self, db, choice, character_id):
        row = self._class_row(db, choice.feature.class_id, character_id)
        if row is None or row.subclass_id is None:
            return []
        return [self.view(db.get(Subclass, row.subclass_id))]

    def save(self, db, choice, character_id, slugs):
        subclass = db.scalar(self.options_query(choice).where(Subclass.slug.in_(slugs)))
        row = self._class_row(db, choice.feature.class_id, character_id)
        if subclass is None or row is None:
            return "That isn't one of the options."
        row.subclass_id = subclass.id
        db.commit()
        return None

    def already_have(self, db, choice, character_id):
        return set()  # one subclass slot per class; nothing to mark

    def picked_choice_ids(self, db, character_id):
        query = (
            select(Choice.id)
            .join(Feature, Choice.feature_id == Feature.id)
            .join(CharacterClassLevel, CharacterClassLevel.class_id == Feature.class_id)
            .where(
                Choice.kind == "subclass",
                CharacterClassLevel.character_id == character_id,
                CharacterClassLevel.subclass_id.is_not(None),
            )
        )
        return set(db.scalars(query))

    def clear(self, db, choice_ids, character_id):
        for choice_id in choice_ids:
            row = self._class_row(db, db.get(Choice, choice_id).feature.class_id, character_id)
            if row is not None:
                row.subclass_id = None


KINDS: dict[str, ChoiceKind] = {
    "option": OptionKind(),
    "skill": SkillKind(),
    "spell": SpellKind(),
    "spellbook": SpellbookKind(),
    "subclass": SubclassKind(),
}

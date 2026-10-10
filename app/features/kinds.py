"""Choice kinds: where a choice's options come from and where a character's picks are saved.

Most kinds work the same way: options are rows of some `target` table, and each pick is a
row in a `pick` table holding (character_id, choice_id, <target>_id). The subclass kind is
the exception: its pick is stored on the character's class row. Adding a new kind of choice
(languages, tools, feats, ...) means adding a subclass here and to KINDS.
"""

from dataclasses import dataclass

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.abilities.models import CharacterAbilityBonus
from app.backgrounds.models import Background
from app.classes.models import CharacterClass, CharacterClassLevel, Subclass
from app.content.queries import available
from app.feats.models import Feat
from app.features.models import CharacterChoicePick, Choice, ChoiceOption, Feature
from app.skills.models import CharacterSkill, CharacterSkillExpertise, Skill
from app.species.models import Species
from app.spells.models import CharacterSpell, Spell, SpellbookEntry


def source_name(db: Session, feature: Feature) -> str:
    """What a feature belongs to, as the player knows it: "Wizard", "Goliath", "Familiar
    Trainer", "Transmuter" or "Familiar Friend"."""
    for model, parent_id in [
        (CharacterClass, feature.class_id),
        (Subclass, feature.subclass_id),
        (Species, feature.species_id),
        (Background, feature.background_id),
        (Feat, feature.feat_id),
    ]:
        if parent_id is not None:
            return db.get(model, parent_id).name
    return feature.name


@dataclass(frozen=True)
class OptionView:
    key: str  # the row's id: what forms submit, since slugs are only unique within a source
    name: str
    summary: str = ""
    detail: str = ""
    group: str = ""  # options with groups are shown in collapsible sections, e.g. spell levels
    school: str = ""  # spells only: enables the school/ritual/name filters
    ritual: bool = False
    warnings: tuple[str, ...] = ()  # rule markers, e.g. "Not on the Wizard list"
    note: str = ""  # e.g. "Copied to spellbook · scroll from the crypt"
    removable: bool = False  # shows a Remove link when the grid is given `removal`


class ChoiceKind:
    target: type  # table the options come from
    pick: type  # table a character's picks are saved in
    target_fk: str  # column on `pick` pointing at `target`
    # Shown on options the character already has from somewhere else (they can't be picked):
    # "<known_from> Wizard" when the pick came from a choice (and known_from is set), else
    # known_label.
    known_label = "Already known"
    known_from: str | None = "Known from"
    noun = ("option", "options")  # for counts like "31 spells"

    def pick_values(self, choice: Choice) -> dict:
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

    def save(self, db: Session, choice: Choice, character_id: int, keys: list[str]) -> str | None:
        """Replace this choice's picks. Returns an error message instead if they aren't valid."""
        ids = [int(k) for k in keys if k.isdigit()]
        targets = db.scalars(self.options_query(choice).where(self.target.id.in_(ids))).all()
        if len(targets) != len(keys):
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
                **self.pick_values(choice),
            )
            for t in targets
        )
        db.commit()
        return None

    def unavailable(self, db: Session, choice: Choice, character_id: int) -> dict[str, str]:
        """{key: why} for options the character can't pick, shown on the choice form, naming
        where they already have it from (e.g. "Proficient from Familiar Trainer")."""
        fk = getattr(self.pick, self.target_fk)
        rows = db.execute(
            select(self.target.id, self.pick.choice_id)
            .join(self.pick, fk == self.target.id)
            .where(
                self.pick.character_id == character_id,
                self.pick.choice_id.is_distinct_from(choice.id),
            )
        )
        result = {}
        for target_id, choice_id in rows:
            other = db.get(Choice, choice_id) if choice_id and self.known_from else None
            result[str(target_id)] = (
                f"{self.known_from} {source_name(db, other.feature)}" if other else self.known_label
            )
        return result

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
            .where(ChoiceOption.choice_id == choice.id, available(ChoiceOption))
            .order_by(ChoiceOption.position)
        )

    def view(self, option):
        return OptionView(str(option.id), option.name, option.summary)


class SkillKind(ChoiceKind):
    """Skill proficiencies. criteria: {"skill_ids": [...]} resolved from slugs on import, or
    {} for any skill (a background's free pick)."""

    target, pick, target_fk = Skill, CharacterSkill, "skill_id"
    known_label = "Already proficient"
    known_from = "Proficient from"

    def options_query(self, choice):
        query = select(Skill).where(available(Skill))
        if "skill_ids" in choice.criteria:
            query = query.where(Skill.id.in_(choice.criteria["skill_ids"]))
        return query.order_by(Skill.name)

    def view(self, skill):
        return OptionView(str(skill.id), skill.name, detail=skill.ability)


class ExpertiseKind(SkillKind):
    """Expertise in a skill the character is already proficient in (Scholar). criteria:
    {"skill_ids": [...]} resolved from slugs on import, or {} for any skill."""

    pick = CharacterSkillExpertise
    known_label = "Already have Expertise"
    known_from = "Expertise from"

    def _proficient(self, db: Session, character_id: int) -> set[int]:
        query = select(CharacterSkill.skill_id).where(CharacterSkill.character_id == character_id)
        return set(db.scalars(query))

    def unavailable(self, db, choice, character_id):
        result = super().unavailable(db, choice, character_id)
        proficient = self._proficient(db, character_id)
        for skill in db.scalars(self.options_query(choice)):
            if skill.id not in proficient:
                result.setdefault(str(skill.id), "Not proficient")
        return result

    def save(self, db, choice, character_id, keys):
        proficient = self._proficient(db, character_id)
        ids = [int(k) for k in keys if k.isdigit()]
        lacking = db.scalars(
            select(Skill.name).where(Skill.id.in_(ids), Skill.id.not_in(proficient))
        ).all()
        if lacking:
            return f"You need proficiency in {', '.join(lacking)} first."
        return super().save(db, choice, character_id, keys)

    def remove_unproficient(self, db: Session, character_id: int) -> None:
        """Drop Expertise in skills the character is no longer proficient in, e.g. after
        re-picking their class skills. Doesn't commit."""
        db.execute(
            delete(CharacterSkillExpertise).where(
                CharacterSkillExpertise.character_id == character_id,
                CharacterSkillExpertise.skill_id.not_in(
                    select(CharacterSkill.skill_id).where(
                        CharacterSkill.character_id == character_id
                    )
                ),
            )
        )


class SpellKind(ChoiceKind):
    """Spells known from a class's list, like cantrips. criteria: {"class_id": ...} plus either
    "level" (an exact spell level) or "max_level" (levels 1 up to it), and optionally "school"
    (Evocation Savant). The class is resolved from its slug on import."""

    target, pick, target_fk = Spell, CharacterSpell, "spell_id"
    noun = ("spell", "spells")

    def options_query(self, choice):
        criteria = choice.criteria
        query = (
            select(Spell)
            .join(Spell.classes)
            .where(CharacterClass.id == criteria["class_id"], available(Spell))
        )
        if "level" in criteria:
            query = query.where(Spell.level == criteria["level"])
        else:
            query = query.where(Spell.level.between(1, criteria["max_level"]))
        if "school" in criteria:
            query = query.where(Spell.school == criteria["school"])
        return query.order_by(Spell.level, Spell.name)

    def view(self, spell):
        group = "Cantrips" if spell.level == 0 else f"Level {spell.level}"
        return OptionView(
            str(spell.id), spell.name, spell.summary, spell.detail, group, spell.school, spell.ritual
        )


class SpellbookKind(SpellKind):
    """Spells written into a Wizard's spellbook on level up, or by a feature like Savant
    (criteria "acquired_via": "feature"). Same options as SpellKind, but picks become spellbook
    entries."""

    pick = SpellbookEntry
    known_label = "In your spellbook"
    known_from = None  # always the Wizard's book; naming it adds nothing

    def pick_values(self, choice):
        return {"acquired_via": choice.criteria.get("acquired_via", "level_up")}


class SubclassKind(ChoiceKind):
    """A class's subclass. The pick is stored on the character's row for that class
    (character_classes.subclass_id), so each class has its own subclass."""

    target = Subclass

    def options_query(self, choice):
        return (
            select(Subclass)
            .where(Subclass.class_id == choice.feature.class_id, available(Subclass))
            .order_by(Subclass.name)
        )

    def view(self, subclass):
        return OptionView(str(subclass.id), subclass.name, subclass.summary)

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

    def save(self, db, choice, character_id, keys):
        ids = [int(k) for k in keys if k.isdigit()]
        subclass = db.scalar(self.options_query(choice).where(Subclass.id.in_(ids)))
        row = self._class_row(db, choice.feature.class_id, character_id)
        if subclass is None or row is None:
            return "That isn't one of the options."
        row.subclass_id = subclass.id
        db.commit()
        return None

    def unavailable(self, db, choice, character_id):
        return {}  # one subclass slot per class; nothing to mark

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


class AbilityScoresKind(ChoiceKind):
    """A background's ability score increases: +2 to one of criteria["from"] and +1 to
    another, or +1 to all three. A pick is one character_ability_bonuses row per ability.
    Scores still can't go above 20; AbilityView applies the cap.

    It has its own form (app/abilities/router.py) rather than the option grid. For the
    generic code, each way of splitting the increases is one option, keyed like "INT2.CON1"."""

    pick = CharacterAbilityBonus
    noun = ("split", "splits")

    def split(self, choice: Choice, plus2: str, plus1: str, even: bool) -> dict[str, int] | None:
        """{ability: amount} for +2/+1 (or +1 to each with `even`), or None if that isn't a
        valid split for this choice."""
        abilities = choice.criteria["from"]
        if even:
            return {a: 1 for a in abilities}
        if plus2 in abilities and plus1 in abilities and plus2 != plus1:
            return {plus2: 2, plus1: 1}
        return None

    def _splits(self, choice: Choice) -> list[dict[str, int]]:
        abilities = choice.criteria["from"]
        splits = [{two: 2, one: 1} for two in abilities for one in abilities if one != two]
        return splits + [{a: 1 for a in abilities}]

    def key(self, amounts: dict[str, int]) -> str:
        return ".".join(f"{abbr}{n}" for abbr, n in amounts.items())

    def _view(self, amounts: dict[str, int]) -> OptionView:
        return OptionView(
            self.key(amounts), ", ".join(f"{abbr} +{n}" for abbr, n in amounts.items())
        )

    def options(self, db, choice):
        return [self._view(split) for split in self._splits(choice)]

    def picked_amounts(self, db: Session, choice: Choice, character_id: int) -> dict[str, int]:
        """{ability: amount} saved for this choice, the +2 first; empty if not picked."""
        rows = db.scalars(
            select(CharacterAbilityBonus).where(
                CharacterAbilityBonus.character_id == character_id,
                CharacterAbilityBonus.choice_id == choice.id,
            )
        ).all()
        order = choice.criteria["from"]
        rows = sorted(rows, key=lambda r: (-r.amount, order.index(r.ability)))
        return {r.ability: r.amount for r in rows}

    def picked(self, db, choice, character_id):
        amounts = self.picked_amounts(db, choice, character_id)
        return [self._view(amounts)] if amounts else []

    def save(self, db, choice, character_id, keys):
        split = next((s for s in self._splits(choice) if [self.key(s)] == keys), None)
        if split is None:
            return "That isn't one of the options."
        self.clear(db, [choice.id], character_id)
        db.add_all(
            CharacterAbilityBonus(
                character_id=character_id, choice_id=choice.id, ability=abbr, amount=n
            )
            for abbr, n in split.items()
        )
        db.commit()
        return None

    def unavailable(self, db, choice, character_id):
        return {}  # bonuses from other choices stack


KINDS: dict[str, ChoiceKind] = {
    "option": OptionKind(),
    "skill": SkillKind(),
    "expertise": ExpertiseKind(),
    "spell": SpellKind(),
    "spellbook": SpellbookKind(),
    "subclass": SubclassKind(),
    "ability_scores": AbilityScoresKind(),
}

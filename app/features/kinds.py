"""Choice kinds: where a choice's options come from and where a character's picks are saved.

Every kind works the same way: options are rows of some `target` table, and each pick is a
row in a `pick` table holding (character_id, choice_id, <target>_id). Adding a new kind of
choice (languages, tools, feats, ...) means adding a subclass here and to KINDS.
"""

from dataclasses import dataclass

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.classes.models import CharacterClass
from app.features.models import CharacterChoicePick, Choice, ChoiceOption
from app.skills.models import CharacterSkill, Skill
from app.spells.models import CharacterSpell, Spell


@dataclass(frozen=True)
class OptionView:
    slug: str
    name: str
    summary: str = ""
    detail: str = ""


class ChoiceKind:
    target: type  # table the options come from
    pick: type  # table a character's picks are saved in
    target_fk: str  # column on `pick` pointing at `target`

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
            self.pick(character_id=character_id, choice_id=choice.id, **{self.target_fk: t.id})
            for t in targets
        )
        db.commit()
        return None


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
    """Skill proficiencies. criteria: {"from": [skill slugs]}"""

    target, pick, target_fk = Skill, CharacterSkill, "skill_id"

    def options_query(self, choice):
        return select(Skill).where(Skill.slug.in_(choice.criteria["from"])).order_by(Skill.name)

    def view(self, skill):
        return OptionView(skill.slug, skill.name, detail=skill.ability)


class SpellKind(ChoiceKind):
    """Spells from a class's spell list. criteria: {"class": class slug, "level": spell level}"""

    target, pick, target_fk = Spell, CharacterSpell, "spell_id"

    def options_query(self, choice):
        return (
            select(Spell)
            .join(Spell.classes)
            .where(
                CharacterClass.slug == choice.criteria["class"],
                Spell.level == choice.criteria["level"],
            )
            .order_by(Spell.name)
        )

    def view(self, spell):
        return OptionView(spell.slug, spell.name, spell.summary, spell.detail)


KINDS: dict[str, ChoiceKind] = {
    "option": OptionKind(),
    "skill": SkillKind(),
    "spell": SpellKind(),
}

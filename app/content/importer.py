"""Writing a validated content pack into the database.

One pack is imported in one transaction: if anything fails, nothing from that pack changes.
Rows are matched by slug within the pack's source and updated in place, so IDs (and every
character's picks pointing at them) survive re-imports. Rows that disappear from a pack are
marked retired rather than deleted, because characters may still reference them.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import CharacterClass, Subclass
from app.content.loader import Pack, discover, import_order, resolve, split_ref
from app.content.models import Source
from app.features.models import Choice, ChoiceOption, Feature
from app.features.schema import ChoiceDef, FeatureDef
from app.skills.models import Skill
from app.species.models import Species
from app.spells.models import Spell

log = logging.getLogger("uvicorn.error")  # shows up in the app's log output


class _Importer:
    def __init__(self, db: Session, pack: Pack, by_slug: dict[str, Pack]):
        self.db = db
        self.pack = pack
        self.by_slug = by_slug
        self.now = datetime.now()
        self.source: Source | None = None

    # --- lookups --------------------------------------------------------------------------

    def _id(self, model, ref: str, kind: str) -> int:
        """Database id for a slug reference, in this pack or one it requires."""
        pack_slug = resolve(ref, kind, self.pack, self.by_slug)
        _, slug = split_ref(ref)
        row = self.db.scalar(
            select(model.id)
            .join(Source, Source.id == model.source_id)
            .where(Source.slug == pack_slug, model.slug == slug)
        )
        if row is None:  # the loader checked references, so the required pack wasn't imported
            raise LookupError(f"{ref!r} isn't in the database; import {pack_slug!r} first")
        return row

    # --- generic upsert -------------------------------------------------------------------

    def _sync_rows(self, model, defs, values, scope=None) -> dict[str, object]:
        """Upsert one content table for this source and retire rows missing from the pack.

        `values(def)` gives the columns to set; `scope` narrows matching (e.g. subclasses
        are unique per class). Returns slug -> row.
        """
        query = select(model).where(model.source_id == self.source.id)
        existing = {self._key(row, scope): row for row in self.db.scalars(query)}
        seen = {}
        for d in defs:
            cols = values(d)
            key = (cols.get(scope), d.slug) if scope else d.slug
            row = existing.get(key)
            if row is None:
                row = model(source_id=self.source.id, slug=d.slug)
                self.db.add(row)
            for column, value in cols.items():
                setattr(row, column, value)
            row.retired_at = None
            seen[key] = row
        for key, row in existing.items():
            if key not in seen and row.retired_at is None:
                row.retired_at = self.now
        self.db.flush()
        return {key[1] if scope else key: row for key, row in seen.items()}

    @staticmethod
    def _key(row, scope):
        return (getattr(row, scope), row.slug) if scope else row.slug

    # --- features -------------------------------------------------------------------------

    def _criteria(self, choice: ChoiceDef) -> dict:
        """Choice rules as written in YAML use slugs; the database stores resolved ids."""
        if choice.kind == "skill":
            return {"skill_ids": [self._id(Skill, ref, "skills") for ref in choice.criteria["from"]]}
        if choice.kind in ("spell", "spellbook"):
            rest = {k: v for k, v in choice.criteria.items() if k != "class"}
            return {"class_id": self._id(CharacterClass, choice.criteria["class"], "classes"), **rest}
        return dict(choice.criteria)

    def _sync_features(self, fk_column: str, parent_id: int, defs: list[FeatureDef]) -> None:
        existing = {
            f.slug: f
            for f in self.db.scalars(select(Feature).where(getattr(Feature, fk_column) == parent_id))
        }
        for position, fdef in enumerate(defs):
            feature = existing.pop(fdef.slug, None)
            if feature is None:
                feature = Feature(slug=fdef.slug, **{fk_column: parent_id})
                self.db.add(feature)
            feature.name = fdef.name
            feature.summary = fdef.summary
            feature.description = fdef.description
            feature.level = fdef.level
            feature.applies_to = fdef.applies_to
            feature.uses = fdef.uses.model_dump() if fdef.uses else None
            feature.slot_recovery = fdef.slot_recovery.model_dump() if fdef.slot_recovery else None
            feature.position = position
            feature.retired_at = None
            self._sync_choices(feature, fdef)
        for feature in existing.values():
            self._retire(feature)

    def _sync_choices(self, feature: Feature, fdef: FeatureDef) -> None:
        existing = {c.slug: c for c in feature.choices}
        for position, cdef in enumerate(fdef.choices):
            choice = existing.pop(cdef.slug, None)
            if choice is None:
                choice = Choice(slug=cdef.slug)
                feature.choices.append(choice)
            choice.name = cdef.name
            choice.kind = cdef.kind
            choice.count = cdef.count
            choice.level = cdef.level
            choice.criteria = self._criteria(cdef)
            choice.in_play = cdef.in_play
            choice.position = position
            choice.retired_at = None

            options = {o.slug: o for o in choice.options}
            for opt_position, odef in enumerate(cdef.options):
                option = options.pop(odef.slug, None)
                if option is None:
                    option = ChoiceOption(slug=odef.slug)
                    choice.options.append(option)
                option.name = odef.name
                option.summary = odef.summary
                option.when = odef.when
                option.damage_reaction = (
                    odef.damage_reaction.model_dump(exclude_none=True)
                    if odef.damage_reaction
                    else None
                )
                option.grants = odef.grants.model_dump() if odef.grants else None
                option.position = opt_position
                option.retired_at = None
            for option in options.values():
                option.retired_at = option.retired_at or self.now
        for choice in existing.values():
            choice.retired_at = choice.retired_at or self.now

    def _retire(self, feature: Feature) -> None:
        feature.retired_at = feature.retired_at or self.now
        for choice in feature.choices:
            choice.retired_at = choice.retired_at or self.now

    def _retire_features_of(self, fk_column: str, parent_ids: list[int]) -> None:
        """Features of a parent that was itself removed from the pack."""
        for feature in self.db.scalars(
            select(Feature).where(getattr(Feature, fk_column).in_(parent_ids))
        ):
            self._retire(feature)

    # --- the pack -------------------------------------------------------------------------

    def run(self) -> None:
        meta = self.pack.meta
        self.source = self.db.scalar(select(Source).where(Source.slug == meta.slug))
        if self.source is None:
            self.source = Source(slug=meta.slug)
            self.db.add(self.source)
        self.source.name = meta.name
        self.source.kind = meta.kind
        self.db.flush()

        self._sync_rows(Skill, self.pack.skills, lambda d: {"name": d.name, "ability": d.ability})
        species = self._sync_rows(
            Species, self.pack.species, lambda d: {"name": d.name, "summary": d.summary}
        )
        classes = self._sync_rows(
            CharacterClass,
            self.pack.classes,
            lambda d: {
                "name": d.name,
                "summary": d.summary,
                "hit_die": d.hit_die,
                "saving_throws": list(d.saving_throws),
                "spellcasting": d.spellcasting.model_dump() if d.spellcasting else None,
            },
        )
        subclasses = self._sync_rows(
            Subclass,
            self.pack.subclasses,
            lambda d: {
                "class_id": self._id(CharacterClass, d.class_, "classes"),
                "name": d.name,
                "summary": d.summary,
            },
            scope="class_id",
        )
        spells = self._sync_rows(
            Spell,
            self.pack.spells,
            lambda d: {
                "name": d.name,
                "level": d.level,
                "school": d.school,
                "casting_unit": d.casting_time.unit,
                "concentration": d.concentration,
                "ritual": d.ritual,
                "summary": d.summary,
                "description": d.description,
                "details": d.details(),
            },
        )
        for d in self.pack.spells:
            spells[d.slug].classes = [
                self.db.get(CharacterClass, self._id(CharacterClass, ref, "classes"))
                for ref in d.classes
            ]

        for d in self.pack.species:
            self._sync_features("species_id", species[d.slug].id, d.features)
        for d in self.pack.classes:
            self._sync_features("class_id", classes[d.slug].id, d.features)
        for d in self.pack.subclasses:
            self._sync_features("subclass_id", subclasses[d.slug].id, d.features)

        # Parents retired from the pack take their features with them.
        for model, column in [
            (Species, "species_id"),
            (CharacterClass, "class_id"),
            (Subclass, "subclass_id"),
        ]:
            retired = self.db.scalars(
                select(model.id).where(
                    model.source_id == self.source.id, model.retired_at.is_not(None)
                )
            ).all()
            if retired:
                self._retire_features_of(column, retired)

        self.source.pack_version = str(meta.version)
        self.source.pack_checksum = self.pack.checksum
        self.source.imported_at = self.now


def import_pack(db: Session, pack: Pack, by_slug: dict[str, Pack]) -> None:
    """Import one validated pack in a single transaction."""
    try:
        _Importer(db, pack, by_slug).run()
        db.commit()
    except Exception:
        db.rollback()
        raise


def import_packs(db: Session, only: str | None = None, force: bool = False) -> bool:
    """Import every valid pack whose files changed since its last import (or all of them with
    `force`). Invalid packs are skipped with their errors logged, and keep their previous data.
    Returns False if any pack was invalid or failed."""
    packs = import_order(discover())
    by_slug = {p.slug: p for p in packs}
    all_ok = True
    for pack in packs:
        if only and pack.slug != only:
            continue
        if not pack.ok:
            all_ok = False
            log.error("Content pack %s is invalid and was skipped:", pack.slug)
            for error in pack.errors:
                log.error("  %s", error)
            continue
        source = db.scalar(select(Source).where(Source.slug == pack.slug))
        if not force and source is not None and source.pack_checksum == pack.checksum:
            log.info("Content pack %s unchanged.", pack.slug)
            continue
        try:
            import_pack(db, pack, by_slug)
            log.info("Content pack %s imported (version %s).", pack.slug, pack.meta.version)
        except Exception:
            all_ok = False
            log.exception("Content pack %s failed to import; nothing was changed.", pack.slug)
    return all_ok

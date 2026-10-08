from sqlalchemy import select
from sqlalchemy.orm import Session

from app.features.models import Choice, ChoiceOption, Feature
from app.features.schema import FeatureDef


def sync_features(
    db: Session, parent_model, fk_column: str, features_by_parent: dict[str, list[FeatureDef]]
) -> None:
    """Insert or update features (and their choices and options) for each parent slug.

    `parent_model` is e.g. CharacterClass and `fk_column` the matching Feature column
    ("class_id"). Like sync_reference_rows, nothing is ever deleted, because characters
    may have picks that point at it.
    """
    parents = {p.slug: p for p in db.scalars(select(parent_model))}
    for parent_slug, feature_defs in features_by_parent.items():
        parent_id = parents[parent_slug].id
        existing = {
            f.slug: f
            for f in db.scalars(select(Feature).where(getattr(Feature, fk_column) == parent_id))
        }
        for position, fdef in enumerate(feature_defs):
            feature = existing.get(fdef.slug)
            if feature is None:
                feature = Feature(slug=fdef.slug, **{fk_column: parent_id})
                db.add(feature)
            feature.name = fdef.name
            feature.summary = fdef.summary
            feature.level = fdef.level
            feature.applies_to = fdef.applies_to
            feature.position = position
            _sync_choices(feature, fdef)
    db.commit()


def _sync_choices(feature: Feature, fdef: FeatureDef) -> None:
    existing = {c.slug: c for c in feature.choices}
    for position, cdef in enumerate(fdef.choices):
        choice = existing.get(cdef.slug)
        if choice is None:
            choice = Choice(slug=cdef.slug)
            feature.choices.append(choice)
        choice.name = cdef.name
        choice.kind = cdef.kind
        choice.count = cdef.count
        choice.criteria = cdef.criteria
        choice.position = position

        existing_options = {o.slug: o for o in choice.options}
        for opt_position, odef in enumerate(cdef.options):
            option = existing_options.get(odef.slug)
            if option is None:
                option = ChoiceOption(slug=odef.slug)
                choice.options.append(option)
            option.name = odef.name
            option.summary = odef.summary
            option.position = opt_position

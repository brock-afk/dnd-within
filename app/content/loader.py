"""Finding, parsing and validating content packs. Nothing here touches the database.

A pack is a folder with a pack.yaml. Its files are parsed into the models in
app/content/schema.py, then every reference (a spell's classes, a subclass's class, skill and
spell choices) is checked against this pack and the packs it requires. Any problem makes the
whole pack invalid, reported with the file it's in.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from app.content.schema import (
    BackgroundDef,
    ClassDef,
    FeatDef,
    ItemDef,
    PackMeta,
    SkillDef,
    SpeciesDef,
    SpellDef,
    SubclassDef,
)
from app.core.config import settings
from app.features.schema import FeatureDef


@dataclass
class Pack:
    path: Path
    meta: PackMeta | None = None
    checksum: str = ""
    skills: list[SkillDef] = field(default_factory=list)
    species: list[SpeciesDef] = field(default_factory=list)
    classes: list[ClassDef] = field(default_factory=list)
    subclasses: list[SubclassDef] = field(default_factory=list)
    spells: list[SpellDef] = field(default_factory=list)
    feats: list[FeatDef] = field(default_factory=list)
    backgrounds: list[BackgroundDef] = field(default_factory=list)
    items: list[ItemDef] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.meta.slug if self.meta else self.path.name

    @property
    def ok(self) -> bool:
        return not self.errors


def content_dirs() -> list[Path]:
    return [Path(p) for p in settings.content_paths.split(":") if p]


def discover() -> list[Pack]:
    """Every pack folder under the configured content paths, parsed and validated."""
    packs = []
    for root in content_dirs():
        if root.is_dir():
            for pack_file in sorted(root.glob("*/pack.yaml")):
                packs.append(_parse(pack_file.parent))
    by_slug = {p.slug: p for p in packs}
    for pack in packs:
        # Check references even when some files failed to parse, so one run reports every
        # problem instead of hiding broken references behind a typo elsewhere.
        if pack.meta is not None:
            _check_references(pack, by_slug)
    return packs


def _checksum(folder: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(folder.rglob("*.yaml")):
        digest.update(str(file.relative_to(folder)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def _read(pack: Pack, file: Path):
    try:
        return yaml.safe_load(file.read_text()) or []
    except yaml.YAMLError as exc:
        pack.errors.append(f"{file}: invalid YAML: {exc}")
        return None


def _validate(pack: Pack, file: Path, model: type[BaseModel], data) -> BaseModel | None:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        label = data.get("slug", "?") if isinstance(data, dict) else "?"
        for err in exc.errors():
            where = ".".join(str(part) for part in err["loc"]) or "(top level)"
            pack.errors.append(f"{file} [{label}] {where}: {err['msg']}")
        return None


def _parse(folder: Path) -> Pack:
    pack = Pack(path=folder, checksum=_checksum(folder))
    data = _read(pack, folder / "pack.yaml")
    pack.meta = _validate(pack, folder / "pack.yaml", PackMeta, data) if data is not None else None
    if pack.meta is None:
        return pack

    def load_list(file: Path, model):
        rows = _read(pack, file)
        if rows is None:
            return []
        if not isinstance(rows, list):
            pack.errors.append(f"{file}: expected a list")
            return []
        return [obj for row in rows if (obj := _validate(pack, file, model, row))]

    def load_each(pattern: str, model):
        items = []
        for file in sorted(folder.glob(pattern)):
            row = _read(pack, file)
            if row is not None and (obj := _validate(pack, file, model, row)):
                items.append(obj)
        return items

    if (folder / "skills.yaml").exists():
        pack.skills = load_list(folder / "skills.yaml", SkillDef)
    pack.species = load_each("species/*.yaml", SpeciesDef)
    pack.classes = load_each("classes/*.yaml", ClassDef)
    seen_subclasses = set()
    for file in sorted(folder.glob("subclasses/*/*.yaml")):
        row = _read(pack, file)
        if row is None or not (sub := _validate(pack, file, SubclassDef, row)):
            continue
        # subclasses/<class>/x.yaml: the folder names the class, so a file can't be misfiled.
        class_slug = split_ref(sub.class_)[1]
        if file.parent.name != class_slug:
            pack.errors.append(
                f"{file}: class is {sub.class_!r} but the folder is for {file.parent.name!r}"
            )
        if (class_slug, sub.slug) in seen_subclasses:
            pack.errors.append(f"{folder}: duplicate {class_slug} subclass slug {sub.slug!r}")
        seen_subclasses.add((class_slug, sub.slug))
        pack.subclasses.append(sub)
    for file in sorted(folder.glob("spells/*.yaml")):
        pack.spells.extend(load_list(file, SpellDef))
    if (folder / "items.yaml").exists():
        pack.items = load_list(folder / "items.yaml", ItemDef)
    pack.feats = load_each("feats/*.yaml", FeatDef)
    pack.backgrounds = load_each("backgrounds/*.yaml", BackgroundDef)

    for kind, items in [
        ("skill", pack.skills),
        ("species", pack.species),
        ("class", pack.classes),
        ("spell", pack.spells),
        ("feat", pack.feats),
        ("background", pack.backgrounds),
        ("item", pack.items),
    ]:
        seen = set()
        for item in items:
            if item.slug in seen:
                pack.errors.append(f"{folder}: duplicate {kind} slug {item.slug!r}")
            seen.add(item.slug)
    return pack


# --- References -----------------------------------------------------------------------------


def split_ref(ref: str) -> tuple[str | None, str]:
    """"phb-2024/wizard" -> ("phb-2024", "wizard"); "wizard" -> (None, "wizard")."""
    pack, _, slug = ref.rpartition("/")
    return (pack or None), slug


def resolve(ref: str, kind: str, pack: Pack, by_slug: dict[str, Pack]) -> str | None:
    """The slug of the pack a reference points into, or None if it doesn't exist.

    A plain slug is looked up in this pack first, then in the packs it requires, in order.
    """
    pack_slug, slug = split_ref(ref)
    candidates = [pack_slug] if pack_slug else [pack.slug, *pack.meta.requires]
    for candidate in candidates:
        target = by_slug.get(candidate)
        if target and slug in {item.slug for item in getattr(target, kind)}:
            return candidate
    return None


def _check_references(pack: Pack, by_slug: dict[str, Pack]) -> None:
    singular = {"classes": "class", "skills": "skill", "spells": "spell", "feats": "feat",
                "items": "item"}

    def check(ref: str, kind: str, where: str):
        if resolve(ref, kind, pack, by_slug) is None:
            pack.errors.append(f"{pack.path}: {where}: unknown {singular[kind]} {ref!r}")

    for required in pack.meta.requires:
        if required not in by_slug:
            pack.errors.append(f"{pack.path}/pack.yaml: requires missing pack {required!r}")
        elif not by_slug[required].ok:
            pack.errors.append(f"{pack.path}/pack.yaml: required pack {required!r} is invalid")

    def check_features(features: list[FeatureDef], owner: str):
        for feature in features:
            for granted in feature.spells:
                check(granted.spell, "spells", f"{owner} > {feature.slug} > spells")
            for choice in feature.choices:
                where = f"{owner} > {feature.slug} > {choice.slug}"
                if choice.kind in ("skill", "expertise"):
                    for ref in choice.criteria.get("from", []):
                        check(ref, "skills", where)
                elif choice.kind in ("spell", "spellbook"):
                    check(choice.criteria["class"], "classes", where)

    for sp in pack.species:
        check_features(sp.features, f"species/{sp.slug}")
    for cl in pack.classes:
        check_features(cl.features, f"classes/{cl.slug}")
    for sub in pack.subclasses:
        check(sub.class_, "classes", f"subclasses/{sub.slug}")
        check_features(sub.features, f"subclasses/{sub.slug}")
    for feat in pack.feats:
        check_features(feat.features, f"feats/{feat.slug}")
    for bg in pack.backgrounds:
        check(bg.feat, "feats", f"backgrounds/{bg.slug}")
        check_features(bg.features, f"backgrounds/{bg.slug}")
    for item in pack.items:
        for content in item.contents:
            check(content.item, "items", f"items/{item.slug} > contents")
    for spell in pack.spells:
        for ref in spell.classes:
            check(ref, "classes", f"spells/{spell.slug}")


def import_order(packs: list[Pack]) -> list[Pack]:
    """Packs sorted so every pack comes after the packs it requires."""
    by_slug = {p.slug: p for p in packs}
    ordered, seen = [], set()

    def visit(pack: Pack, stack: tuple[str, ...] = ()):
        if pack.slug in seen:
            return
        if pack.slug in stack:
            pack.errors.append(f"{pack.path}/pack.yaml: circular requires via {' -> '.join(stack)}")
            return
        for required in pack.meta.requires if pack.meta else []:
            if required in by_slug:
                visit(by_slug[required], (*stack, pack.slug))
        seen.add(pack.slug)
        ordered.append(pack)

    for pack in packs:
        visit(pack)
    return ordered

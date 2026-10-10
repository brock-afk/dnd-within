"""Content pack commands.

    python -m app.content check                  validate every pack; exit 1 on errors
    python -m app.content import [PACK] [--force]  import changed packs (or PACK); --force
                                                 re-imports even if unchanged
"""

import argparse
import logging
import sys

from app import models  # noqa: F401  (registers every table)
from app.content.importer import import_packs
from app.content.loader import discover
from app.core.db import SessionLocal


def check() -> int:
    packs = discover()
    if not packs:
        print("No content packs found.")
        return 1
    failed = False
    for pack in packs:
        if pack.ok:
            print(
                f"{pack.slug}: ok ({len(pack.classes)} classes, {len(pack.subclasses)} subclasses, "
                f"{len(pack.species)} species, {len(pack.backgrounds)} backgrounds, "
                f"{len(pack.feats)} feats, {len(pack.skills)} skills, {len(pack.spells)} spells, "
                f"{len(pack.items)} items)"
            )
        else:
            failed = True
            print(f"{pack.slug}: {len(pack.errors)} problem(s)")
            for error in pack.errors:
                print(f"  {error}")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.content")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate every content pack")
    imp = sub.add_parser("import", help="import changed content packs")
    imp.add_argument("pack", nargs="?", help="only this pack")
    imp.add_argument("--force", action="store_true", help="import even if unchanged")
    args = parser.parse_args()

    if args.command == "check":
        return check()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with SessionLocal() as db:
        return 0 if import_packs(db, only=args.pack, force=args.force) else 1


if __name__ == "__main__":
    sys.exit(main())

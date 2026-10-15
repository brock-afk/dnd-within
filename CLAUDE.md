# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A D&D character builder and play sheet that follows the **2024 Player's Handbook (5.5e)** rules. It's a server-rendered FastAPI + Jinja2 + htmx app on MySQL (SQLAlchemy 2, Alembic), managed with `uv` and Python 3.15. There is no JS framework: the only scripts are `app/static/*.js` and vendored htmx.

## Commands

Everything runs through Docker Compose. `dev.sh` wraps the dev overrides (bind mount + uvicorn `--reload`):

```bash
./dev.sh                       # build and start app + MySQL at http://127.0.0.1:8000
./dev.sh logs -f app           # any other args pass through to docker compose
./dev.sh down
```

Migrations run automatically (`alembic upgrade head`) when the app container starts.

```bash
uv run alembic revision --autogenerate -m "describe change"   # run on the HOST so the file isn't root-owned
./dev.sh exec app alembic upgrade head
./dev.sh exec app alembic downgrade -1
```

Content packs:

```bash
./dev.sh exec app python -m app.content check                  # validate every pack, exit 1 on errors
./dev.sh exec app python -m app.content import [PACK] [--force]
```

Tests and lint run on the host:

```bash
uv run pytest                                          # everything; integration tests need the dev MySQL up
uv run pytest --ignore=tests/integration               # pure rules.py modules + content packs, no database
uv run ruff check --fix . && uv run ruff format .
```

`tests/integration/` runs on a real MySQL database, `dnd_within_test` (never the dev data). It is migrated to head and loaded with the committed packs once per run, and every test is rolled back. A fresh dev volume creates it from `scripts/test-db.sql`. No mocks: anything needing the database is an integration test.

CI's `check` job (ruff, pytest on MySQL started from the compose files) gates build and deploy. A project hook in `.claude/settings.json` runs ruff on every `.py` file Claude edits.

Deploying: to Azure, being set up step by step (infrastructure as code in `infra/`, delivery through GitHub Actions). Database helpers (the server ones run through the Ops workflow, `.github/workflows/ops.yml`, not SSH):

```bash
scripts/dump-dev-db.sh                # local: dump the dev database
scripts/restore-db.sh <file or blob>  # server: back up, then load a dump (local file or a blob in db-backups)
scripts/backup.sh                     # server: daily (systemd timer) and before each deploy; uploads to blob storage
scripts/restore-drill.sh              # server: restore the newest blob into a scratch DB and compare row counts
```

`INVITE_CODE` gates registration. Keep the app a single process: live shared views notify in-process (`app/sharing/live.py`).

## Workflow

- New or changed rule logic comes with a test in `tests/`.
- UI, template or htmx changes: check them in the running app (`/run`).
- Before committing: `/simplify`, then `/code-review` on the diff (`high` for rules, importer, migrations).
- Changes to `auth/`, `sharing/`, `homebrew/` or anything public-facing: `/security-review`.

## Architecture

### Domain packages
`app/<domain>/` holds one area each (`auth`, `characters`, `abilities`, `classes`, `species`, `backgrounds`, `feats`, `skills`, `spells`, `features`, `leveling`, `sheet`, `content`). A domain has some of these modules:
- `models.py`: SQLAlchemy tables
- `router.py`: routes, registered in `app/main.py`
- `service.py` / `queries.py`: DB-backed logic and view dataclasses
- `rules.py`: pure 2024 PHB rule math with no DB access, documented in docstrings
- `templates/<domain>/`: Jinja templates, referenced as `"<domain>/x.html"`

`app/core/` (config, db, templates) must never import from domains. `app/models.py` imports every domain's models so `Base.metadata` is complete. Alembic and the app both rely on it, so **any new models module must be added there**.

### Data-driven content
Game content (classes, subclasses, species, skills, spells, and their features/choices) lives as YAML in **content packs**, not in code:
- `content/<pack>/pack.yaml` plus `classes/`, `subclasses/<class>/`, `species/`, `backgrounds/`, `feats/`, `spells/level-N.yaml`, `skills.yaml`.
- `content-private/` holds third-party, copyrighted packs. It is gitignored and never built into the image. `CONTENT_PATHS` (default `content:content-private`) controls where packs are discovered.
- `app/content/loader.py` parses packs into Pydantic models (`app/content/schema.py`, `app/features/schema.py`; all `extra="forbid"`) and checks cross-references. A reference can be a plain slug, which is looked up in this pack and then its `requires`, or `pack/slug`. It never touches the DB.
- `app/content/importer.py` upserts each pack in one transaction on app startup, but only when the pack's checksum changed. Rows are matched by slug within their `Source` and updated in place, so IDs survive re-imports. Rows that disappear from a pack are **retired, not deleted**, because characters reference them.

Adding a new content capability usually means changing these together: the YAML schema (`*/schema.py`), the loader's reference checks, the importer, the DB model, and a migration.

### Features and choices
`Feature` rows belong to exactly one of a class, species, subclass, background, or feat (enforced by a check constraint). A background's origin feat applies through `characters.background_id`; species, background and feat features unlock by character level. Features carry mechanics like `uses`, `rolled_dice`, `slot_recovery`, and damage reactions. A `Choice` on a feature has a `kind` (`option`, `skill`, `expertise`, `spell`, `spellbook`, `subclass`, `ability_scores`). A choice offering exactly as many options as it asks for is auto-picked by `fill_fixed_choices` when a background is set. `app/features/kinds.py` maps each kind to the table its options come from and the table picks are saved in. To add a new kind of choice (languages, feats, …), subclass `ChoiceKind` and register it in `KINDS`.

### Two character views
- **Build** (`/characters/{id}`, `characters/page.py`): leveling, ability scores, and feature choices.
- **Play** (`/characters/{id}/sheet`, `app/sheet/`): HP, temp HP, HP/AC effects, spell slots, prepared spells, feature uses, and short/long rests (`rests.py`).

Stored vs. derived: max HP, AC, and slot maximums are calculated. Current HP is stored, with `NULL` meaning "at full". Max-HP changes must go through `sheet.rules.apply_max_change` / `track_max_change` so current HP follows the PHB rules in its docstring.

### htmx response patterns (`app/core/templates.py`)
- Routes that change a character re-render the full page and wrap it with `morph_in_place(response, selector)`. htmx then morphs only that element, keeping scroll and focus. See `refresh_character_page` in `characters/page.py`.
- `hx_redirect(path)` triggers a full navigation. `form_error(...)` renders an inline error partial.
- Reference static assets in templates with `static_url("file.js")`, which adds a content hash for cache busting.

### Database conventions
- `Base` in `app/core/db.py` sets a naming convention for every index and constraint, so migrations refer to deterministic names. Keep it when writing manual migrations.
- Migration filenames are date-prefixed (`alembic.ini` `file_template`).
- Use the `DbSession` dependency for routes, `CurrentUser` for auth, and `OwnedCharacter` (`app/characters/dependencies.py`) to load a character the user owns.

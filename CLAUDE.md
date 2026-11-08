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

CI's `check` job (ruff, pytest on MySQL started from the compose files) gates the image build. A project hook in `.claude/settings.json` runs ruff on every `.py` file Claude edits.

Deploying: to Azure, being set up step by step (infrastructure as code in `infra/`, delivery through GitHub Actions). A merge to main builds and scans the image and tags it `:<sha>` and `:latest`; nothing deploys. `gh release create vX.Y.Z --target main --title vX.Y.Z --generate-notes` releases it (`release.yml`: deploys that image, moves `:deployed`). To roll back, Run workflow on Release with an older tag; across a migration, restore the backup taken before the newer release first. Database helpers (the server ones run through the Ops workflow, `.github/workflows/ops.yml`, not SSH):

```bash
scripts/dump-dev-db.sh                # local: dump the dev database
scripts/restore-db.sh <file or blob>  # server: back up, then load a dump (local file or a blob in db-backups)
scripts/content-release.sh <tag>      # server, over SSH for now: install and import a content release
scripts/backup.sh                     # server: daily (systemd timer) and before each deploy; uploads to blob storage
scripts/restore-drill.sh              # server: restore the newest blob into a scratch DB and compare row counts
```

`INVITE_CODE` gates registration. Keep the app a single process: live shared views notify in-process (`app/sharing/live.py`).

## Workflow

- New or changed rule logic comes with a test in `tests/`.
- UI, template or htmx changes: check them in the running app (`/run`).
- Before committing: `/simplify`, then `/code-review` on the diff (`high` for rules, importer, migrations).
- Changes to `auth/`, `sharing/`, `homebrew/` or anything public-facing: `/security-review`.
- No comments or docstrings, in any file, unless one is absolutely necessary. Code that seems to need a comment should be made clearer instead: a better name, a named constant, a smaller function, or a test that pins the behaviour. Lint directives (`# noqa`) and functional headers (`#!`, `# syntax=`, `#cloud-config`) are not comments.

## Architecture

### Domain packages
`app/<domain>/` holds one area each (`auth`, `characters`, `abilities`, `classes`, `species`, `backgrounds`, `feats`, `skills`, `spells`, `features`, `leveling`, `sheet`, `inventory`, `homebrew`, `sharing`, `content`). A domain has some of these modules:
- `models.py`: SQLAlchemy tables
- `router.py`: routes, registered in `app/main.py`. A route loads its rows through a dependency, runs one service operation, builds a view with a `queries.py` builder and renders it with a `page.py` function. Routers don't import SQLAlchemy, templates, `HTTPException` or Pydantic, and don't construct models.
- `dependencies.py`: `Annotated` loaders such as `OwnedCharacter`, `OwnedItemRow` and `SharedCharacter`. A missing row, another user's row and a row of the wrong kind for the route all get a 404, so ids can't be probed. Child rows use `characters/dependencies.py:owned_child`.
- `form.py`: Pydantic models for submitted forms, parsed with `core/forms.py` (`parse_id`, `parse_int`, `parse_amount`; never `isdigit()` and `int()`). It may read the database for a lookup a check needs, but never writes.
- `queries.py`: read lookups, frozen view dataclasses (never raw dicts) and the builders that fill them. A builder does the reload after a change. A lookup by id uses the same query as the list the id came from (`content/queries.py:picked_row`). It never imports a service.
- `service.py`: operations. Each checks first, then writes, and returns its errors (a message as `str | None`, or field errors as `dict[str, str]`) with nothing changed when there are any. Operations flush; `get_db` commits once per request.
- `page.py`: render functions taking the request, a view and an optional error. No database access. The view's fields become the template context (`core/templates.py:view_context`).
- `rules.py`: pure 2024 PHB rule math and constants with no DB access; anything may import it
- `templates/<domain>/`: Jinja templates, referenced as `"<domain>/x.html"`

`app/core/` (config, db, templates) must never import from domains. `app/models.py` imports every domain's models so `Base.metadata` is complete. Alembic and the app both rely on it, so **any new models module must be added there**.

### Data-driven content
Game content (classes, subclasses, species, skills, spells, and their features/choices) lives as YAML in **content packs**, not in code:
- `<pack>/pack.yaml` plus `classes/`, `subclasses/<class>/`, `species/`, `backgrounds/`, `feats/`, `spells/level-N.yaml`, `skills.yaml`.
- Packs are copyrighted and live in the private `dnd-within-content` repo, never here or in the image. Both compose files mount it at `/app/content-private`. `CONTENT_PATHS` (default `content-private`) controls where packs are discovered. Tests use only `tests/fixtures/content`.
- `app/content/loader.py` parses packs into Pydantic models (`app/content/schema.py`, `app/features/schema.py`; all `extra="forbid"`) and checks cross-references. A reference can be a plain slug, which is looked up in this pack and then its `requires`, or `pack/slug`. It never touches the DB.
- `app/content/importer.py` upserts each pack in one transaction when `python -m app.content import` runs (never on app startup), but only when the pack's checksum changed. Rows are matched by slug within their `Source` and updated in place, so IDs survive re-imports. Rows that disappear from a pack are **retired, not deleted**, because characters reference them.

Adding a new content capability usually means changing these together: the YAML schema (`*/schema.py`), the loader's reference checks, the importer, the DB model, and a migration.

### Features and choices
`Feature` rows belong to exactly one of a class, species, subclass, background, feat, item, or choice option (enforced by a check constraint). A background's origin feat applies through `characters.background_id`; species, background and feat features unlock by character level. An option's features (a Fiendish Legacy's spells) apply while it's picked and unlock by the same level as the feature offering the choice. Features carry mechanics like `uses`, `spells` (always prepared, or cast free by spending uses), `grants`, and `slot_recovery`; options can also carry damage reactions. On the Play sheet, features with uses always show (Features section). A feature or picked option without uses shows only where its content places it: `action` or `when` puts it in Features under that action type (Actions, Bonus Actions, Reactions, Triggered), and `sheet` puts a passive one in an Attributes row (`senses`, `saves`, `speed`, `resistances`, `traits`). `sheet: none` marks one as Build page only on purpose. `python -m app.content check` lists any that would otherwise appear only on the Build page. A `Choice` on a feature has a `kind` (`option`, `skill`, `expertise`, `spell`, `spellbook`, `subclass`, `ability_scores`). A choice offering exactly as many options as it asks for is auto-picked by `fill_fixed_choices` when a background is set. `app/features/kinds.py` maps each kind to the table its options come from and the table picks are saved in. To add a new kind of choice (languages, feats, …), subclass `ChoiceKind` and register it in `KINDS`.

### Two character views
- **Build** (`/characters/{id}`, `characters/page.py`): leveling, ability scores, and feature choices.
- **Play** (`/characters/{id}/sheet`, `app/sheet/`): HP, temp HP, HP/AC effects, spell slots, prepared spells, feature uses, and short/long rests.

Stored vs. derived: max HP, AC, and slot maximums are calculated. Current HP is stored, with `NULL` meaning "at full". Max-HP changes must happen inside `sheet.service.tracking_max_hp` so current HP follows the PHB rules in `sheet.rules.apply_max_change`.

### htmx response patterns (`app/core/templates.py`)
- Routes that change a character re-render the full page and wrap it with `morph_in_place(response, selector)`. htmx then morphs only that element, keeping scroll and focus. On the Build page, routes build the view with `characters/queries.py:refreshed_build_view` (it reloads what the change touched) and render it with `characters/page.py:refresh_build`.
- `hx_redirect(path)` triggers a full navigation. `form_error(...)` renders an inline error partial.
- Reference static assets in templates with `static_url("file.js")`, which adds a content hash for cache busting.

### Database conventions
- `Base` in `app/core/db.py` sets a naming convention for every index and constraint, so migrations refer to deterministic names. Keep it when writing manual migrations.
- Migration filenames are date-prefixed (`alembic.ini` `file_template`).
- Use the `DbSession` dependency for routes, `CurrentUser` for auth, and `OwnedCharacter` (`app/characters/dependencies.py`) to load a character the user owns.

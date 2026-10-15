# DnD Within

A D&D character builder and play sheet for the 2024 Player's Handbook (5.5e).

- **Build view:** leveling, ability scores, feature and spell choices.
- **Play view:** HP and temp HP, AC, spell slots, prepared spells, feature uses, inventory and attunement, and short and long rests.
- **Sharing:** read-only share links for the DM that update live.
- **Homebrew:** a per-user item editor.

FastAPI, Jinja2 and htmx on MySQL 8.4 (SQLAlchemy 2, Alembic). Python 3.15, managed with `uv`. Game content comes from YAML content packs, not code.

## Local development

Needs Docker and `uv`.

```bash
cp .env.example .env      # set SECRET_KEY
./dev.sh                  # app + MySQL at http://127.0.0.1:8000, with reload
./dev.sh logs -f app      # other args pass through to docker compose
./dev.sh down
```

Migrations run on container start. Create new ones on the host so the files aren't root-owned:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

### Tests and lint

```bash
uv run pytest                                  # integration tests need the dev MySQL running
uv run pytest --ignore=tests/integration       # rules and content packs only
uv run ruff check --fix . && uv run ruff format .
```

Integration tests use a separate `dnd_within_test` database, never the dev data. There are no mocks.

### Content packs

Packs live in `content/` (committed) and `content-private/` (third-party, gitignored, never in the image). They import on startup when their checksum changes.

```bash
./dev.sh exec app python -m app.content check             # validate every pack
./dev.sh exec app python -m app.content import [PACK] [--force]
```

## Production

One Azure VM in `centralus` running Docker Compose: Caddy (automatic HTTPS) in front of the app, with MySQL on a data disk.

```
GitHub Actions ──OIDC──▶ Azure ──▶ ACR (rg-dndwithin-shared)
                               └─▶ az vm run-command ──▶ vm-dndwithin-app (rg-dndwithin-iaas)
                                                         Caddy :443 ─▶ app :8000 ─▶ MySQL
```

### Infrastructure

Bicep in `infra/bicep/` (see its README). `bootstrap.bicep` holds policy, custom roles and the CI identities, and you run it by hand. `main.bicep` holds the workload: registry, network and VM.

`.github/workflows/infra.yml` lints both templates and posts a what-if for `main.bicep` on every pull request that touches `infra/`, using a read-only identity. To deploy, start the workflow on `main` with **Run workflow**. That run deploys `main.bicep` with an identity that holds Contributor on the two resource groups and can only assign the roles the templates use.
It also needs the repository variables `AZURE_INFRA_CLIENT_ID`, `AZURE_WHATIF_CLIENT_ID`, `SSH_SOURCE_ADDRESS` and `SSH_PUBLIC_KEY`.

### Delivery

`.github/workflows/app.yml` runs `check` on every pull request, and the whole pipeline on every push to `main` (except `infra/` and Markdown):

1. **check:** ruff and pytest against MySQL started from the compose files.
2. **build:** multi-arch image pushed to ACR, tagged with the commit SHA, then scanned with Trivy. A fixable HIGH or CRITICAL vulnerability stops the deploy.
3. **deploy:** `az vm run-command` ships the compose files, Caddyfile and `scripts/` to `/opt/dnd-within` and runs `scripts/deploy-vm.sh`, which pulls the image and restarts the stack, waiting until every container is healthy. Then a smoke test fetches `https://<site>/healthz`.

Actions, base images and Python packages are pinned; Dependabot (`.github/dependabot.yml`) opens weekly update PRs.

The workflow logs in through OIDC with no stored secrets. It needs the repository variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`.

### Server setup

Copy `.env.production.example` to `/opt/dnd-within/.env` and fill in every value. `INVITE_CODE` gates registration; leaving it empty opens sign-up. Third-party packs go in `/opt/dnd-within/content-private/`.

Keep the app a single process: live shared views (`app/sharing/live.py`) and login rate limits (`app/auth/limits.py`) are held in memory, so extra processes would delay live updates by up to 60 s and multiply allowed guesses. Running more than one would need a shared store for both, such as MySQL or Redis.

### Backups

```bash
scripts/backup.sh                     # server, daily from cron; keeps the newest 14
scripts/restore-db.sh <dump.sql.gz>   # server; stops and restarts the app
scripts/dump-dev-db.sh                # local dev database
```

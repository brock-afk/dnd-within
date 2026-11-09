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

Packs are copyrighted, so they live in the private `dnd-within-content` repo, never in this repo or the image. Clone it next to this one: `docker-compose.dev.yml` mounts `../dnd-within-content` at `/app/content-private`. The app doesn't import packs on startup: after changing one, run the import command below. Tests use only `tests/fixtures/content`.

```bash
./dev.sh exec app python -m app.content check             # validate every pack
./dev.sh exec app python -m app.content import [PACK] [--force]
```

## Production

One Azure VM in `centralus` running Docker Compose: Caddy (automatic HTTPS) in front of the app, with MySQL on a data disk. See [docs/architecture.md](docs/architecture.md) for the full design: identities and permissions, delivery, data protection, monitoring, and known limitations.

```
GitHub Actions ──OIDC──▶ Azure ──▶ ACR (rg-dndwithin-shared)
                               └─▶ az vm run-command ──▶ vm-dndwithin-app (rg-dndwithin-iaas)
                                                         Caddy :443 ─▶ app :8000 ─▶ MySQL
```

### Infrastructure

Bicep in `infra/bicep/` (see its README). `bootstrap.bicep` contains policy, custom roles, the CI identities and their role assignments, and resource locks; an Owner deploys it manually. `main.bicep` contains the workload: registry, network, VM, backup storage, Key Vault, Recovery Services vault and monitoring.

`.github/workflows/infra.yml` lints both templates on pull requests that change `infra/` and runs a what-if for `main.bicep` as a read-only identity. Deployment runs when the workflow is started manually on `main`, as an identity with Contributor on the two resource groups and role assignment rights limited to the roles the templates use. The workflow needs the repository variables `AZURE_INFRA_CLIENT_ID`, `AZURE_WHATIF_CLIENT_ID` and `SSH_PUBLIC_KEY`, and the repository secrets `SSH_SOURCE_ADDRESS` and `ALERT_EMAIL`.

### Delivery

`.github/workflows/app.yml` runs `check` on every pull request, and on every push to `main` also builds the image. Nothing deploys on a merge.

1. **check:** ruff and pytest against MySQL started from the compose files.
2. **build:** multi-arch image pushed to ACR as `candidate-<sha>` and scanned with Trivy. Only if no fixable HIGH or CRITICAL vulnerability is found is it tagged `<sha>` and `latest`.

`.github/workflows/release.yml` deploys a release: `gh release create vX.Y.Z --target main --title vX.Y.Z --generate-notes`. It runs in the `Production` environment, finds the scanned `<sha>` image for the tagged commit and pins its digest, then `az vm run-command` ships the compose files, Caddyfile and `scripts/` to `/opt/dnd-within` and runs `scripts/deploy-vm.sh`, which pulls the image and restarts the stack, waiting until every container is healthy. It then tags the image `vX.Y.Z` and `deployed`, and a smoke test fetches `https://<site>/healthz`. To roll back, run Release by hand with an older tag selected under **Use workflow from**. Migrations only go forward, so rolling back across one needs the backup taken before the newer release restored first.

`.github/workflows/ops.yml` runs server operations without SSH, through the same run-command access and the same `Production` environment: **Run workflow** with `backup`, `restore-drill`, or `restore` (a blob name in `db-backups`, confirmed by typing `RESTORE`). The restore drill also runs monthly on its own. To restore a dump from your machine, upload it first: `az storage blob upload --auth-mode login --account-name stdndwithincsiqze -c db-backups -f <dump.sql.gz>`.

Actions, base images and Python packages are pinned; Dependabot (`.github/dependabot.yml`) opens weekly update PRs.

The workflows log in through OIDC with no stored secrets. They need the repository variables `AZURE_CLIENT_ID` (App), `AZURE_RELEASE_CLIENT_ID` (Release and Ops), `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`. The release identity trusts any job in the `Production` environment, so that environment's deployment policy (branch `main` for Ops, tags `v*` for Release) is part of the access control.

### Server setup

Copy `.env.production.example` to `/opt/dnd-within/.env` and fill in every value. Registration needs a one-time invite link, made on the admin page (`/admin/invites`). After the first deploy with invites, make your account an admin once by running the Ops workflow with `grant-admin` and your username (`revoke-admin` takes it away). On an empty database, `python -m app.auth create-admin` in the app container creates one interactively. Content packs are installed from a release of the `dnd-within-content` repo with `ssh az-dnd 'bash /opt/dnd-within/scripts/content-release.sh <tag>'`, which downloads it from the `content-releases` container, checks it with the running image, puts it in `/opt/dnd-within/content-private/` and imports it.

Keep the app a single process: live shared views (`app/sharing/live.py`) and login rate limits (`app/auth/limits.py`) are held in memory, so extra processes would delay live updates by up to 60 s and multiply allowed guesses. Running more than one would need a shared store for both, such as MySQL or Redis.

### Backups

```bash
scripts/backup.sh                     # server: daily (systemd timer) and before each deploy; uploads to blob storage
scripts/restore-drill.sh              # server: restore the newest blob into a scratch DB and compare row counts
scripts/restore-db.sh <file or blob>  # server: back up, then load a dump (local file or a blob in db-backups)
scripts/content-release.sh <tag>      # server: install and import a content release from content-releases
scripts/dump-dev-db.sh                # local dev database
```

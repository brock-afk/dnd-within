#!/usr/bin/env bash
# Run docker compose with the dev overrides (live reload).
#   ./dev.sh              build and start the dev stack
#   ./dev.sh <args...>    pass anything else through, e.g. ./dev.sh down, ./dev.sh logs -f app
#
# Database migrations (Alembic) run automatically when the app container starts.
#   uv run alembic revision --autogenerate -m "add widgets"   create a migration from model changes
#                                                             (run on the host so the file isn't owned by root)
#   ./dev.sh exec app alembic upgrade head                    apply migrations without a restart
#   ./dev.sh exec app alembic downgrade -1                    undo the latest migration
set -euo pipefail
cd "$(dirname "$0")"

compose=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)

if [[ $# -eq 0 ]]; then
    exec "${compose[@]}" up --build
fi
exec "${compose[@]}" "$@"

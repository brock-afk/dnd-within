#!/usr/bin/env bash
# Run docker compose with the dev overrides (live reload).
#   ./dev.sh              build and start the dev stack
#   ./dev.sh <args...>    pass anything else through, e.g. ./dev.sh down, ./dev.sh logs -f app
set -euo pipefail
cd "$(dirname "$0")"

compose=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)

if [[ $# -eq 0 ]]; then
    exec "${compose[@]}" up --build
fi
exec "${compose[@]}" "$@"

#!/usr/bin/env bash
# Load a database dump into the production database (run on the server):
#   scripts/restore-db.sh dnd_within-2026-10-10-1200.sql.gz
# Replaces every table in the dump. The app is stopped meanwhile and started again after;
# a dump made by this app includes its migration version, so startup has nothing to migrate.
set -euo pipefail
cd "$(dirname "$0")/.."
dump="${1:?usage: scripts/restore-db.sh <dump.sql.gz>}"
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

"${compose[@]}" stop app
gunzip -c "$dump" | "${compose[@]}" exec -T db sh -c \
    'exec mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
"${compose[@]}" start app
echo "Restored $dump"

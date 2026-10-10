#!/usr/bin/env bash
# Dump the local dev database (run on your machine): writes dnd_within-<date>.sql.gz here.
# Copy it to the server and load it with scripts/restore-db.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
out="dnd_within-$(date +%F-%H%M).sql.gz"
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T db sh -c \
    'exec mysqldump --single-transaction --no-tablespaces -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    | gzip > "$out"
echo "Wrote $out"

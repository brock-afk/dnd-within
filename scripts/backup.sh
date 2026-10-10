#!/usr/bin/env bash
# Back up the production database (run on the server, daily from cron):
#   15 4 * * * cd /opt/dnd-within && scripts/backup.sh >> backups/backup.log 2>&1
# Writes backups/dnd_within-<date>.sql.gz and keeps the newest 14.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/dnd_within-$(date +%F-%H%M).sql.gz"
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db sh -c \
    'exec mysqldump --single-transaction --no-tablespaces -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    | gzip > "$out"
ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm --
echo "$(date -Is) wrote $out"

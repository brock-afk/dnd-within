#!/usr/bin/env bash
# Load a database dump into the production database (run on the server as root):
#   scripts/restore-db.sh backups/dnd_within-2026-10-10-120000.sql.gz   # a local file
#   scripts/restore-db.sh dnd_within-2026-10-10-120000.sql.gz           # a blob in db-backups
# Replaces every table in the dump. The app is stopped meanwhile and started again after;
# a dump made by this app includes its migration version, so startup has nothing to migrate.
set -euo pipefail
cd "$(dirname "$0")/.."
dump="${1:?usage: scripts/restore-db.sh <dump.sql.gz | blob name>}"
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

# A blob uploaded from a laptop (az storage blob upload --auth-mode login) restores without SSH.
if [ ! -f "$dump" ]; then
    account=$(sed -n 's/^BACKUP_ACCOUNT=//p' .env)
    mkdir -p backups
    az login --identity --allow-no-subscriptions --output none
    az storage blob download --auth-mode login --account-name "${account:?BACKUP_ACCOUNT missing from .env}" \
        --container-name db-backups --name "$dump" --file "backups/$dump" --only-show-errors --output none
    dump="backups/$dump"
fi

# Restoring the wrong dump is otherwise unrecoverable.
scripts/backup.sh

"${compose[@]}" stop app
gunzip -c "$dump" | "${compose[@]}" exec -T db sh -c \
    'exec mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
"${compose[@]}" start app
echo "Restored $dump"

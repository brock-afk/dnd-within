#!/usr/bin/env bash
# Prove the newest offsite backup restores (run on the server as root, e.g. monthly):
#   scripts/restore-drill.sh
# Loads it into a scratch database next to the live one, compares row counts, and drops it.
# The live database and the app are never touched.
set -euo pipefail
cd "$(dirname "$0")/.."
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
drill=dnd_within_drill

account=$(sed -n 's/^BACKUP_ACCOUNT=//p' .env)
az login --identity --allow-no-subscriptions --output none
blob=$(az storage blob list --auth-mode login --account-name "${account:?BACKUP_ACCOUNT missing from .env}" \
    --container-name db-backups --query 'sort_by(@, &properties.lastModified)[-1].name' -o tsv)
mkdir -p backups
az storage blob download --auth-mode login --account-name "$account" --container-name db-backups \
    --name "$blob" --file "backups/drill.sql.gz" --only-show-errors --output none

sql() { "${compose[@]}" exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -N -u root "$@"' sh "$@"; }
# Exact counts, not information_schema estimates.
counts() {
    local tables
    tables=$(sql -e "SELECT table_name FROM information_schema.tables WHERE table_schema = '$1' ORDER BY 1")
    for t in $tables; do echo "$t $(sql "$1" -e "SELECT COUNT(*) FROM \`$t\`")"; done | LC_ALL=C sort
}
trap 'sql -e "DROP DATABASE IF EXISTS $drill"; rm -f backups/drill.sql.gz backups/drill.txt' EXIT

sql -e "DROP DATABASE IF EXISTS $drill; CREATE DATABASE $drill"
gunzip -c backups/drill.sql.gz | sql "$drill"

live_db=$("${compose[@]}" exec -T db sh -c 'echo "$MYSQL_DATABASE"')
echo "table drill live"
LC_ALL=C join <(counts "$drill") <(counts "$live_db") -a 1 -a 2 -e missing -o 0,1.2,2.2 | tee backups/drill.txt
# Rows added since the backup are expected; a missing or empty table is not.
if grep -q missing backups/drill.txt || awk '$2 == 0 && $3 > 0 { bad = 1 } END { exit !bad }' backups/drill.txt; then
    echo "Restore drill FAILED: $blob"
    exit 1
fi
echo "Restore drill passed: $blob"

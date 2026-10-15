#!/usr/bin/env bash
# Back up the production database (run on the server as root): daily by the dnd-within-backup
# systemd timer, and by deploy-vm.sh before every deploy.
# Writes backups/dnd_within-<date>.sql.gz, uploads it to the db-backups container in the
# BACKUP_ACCOUNT storage account (.env), and keeps the newest 14 locally.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
out="backups/dnd_within-$(date -u +%F-%H%M%S).sql.gz"
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db sh -c \
    'exec mysqldump --single-transaction --no-tablespaces -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' \
    | gzip > "$out.partial"
# Only a finished dump gets the real name, so a failure never leaves a truncated "backup".
mv "$out.partial" "$out"

# The local copy dies with the VM.
account=$(sed -n 's/^BACKUP_ACCOUNT=//p' .env)
az login --identity --allow-no-subscriptions --output none
az storage blob upload --auth-mode login --account-name "${account:?BACKUP_ACCOUNT missing from .env}" \
    --container-name db-backups --file "$out" --name "$(basename "$out")" --only-show-errors --output none

ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm --
echo "$(date -Is) wrote $out and uploaded it to $account"

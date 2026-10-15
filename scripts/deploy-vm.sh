#!/usr/bin/env bash
# Runs on the VM as root with bash, through az vm run-command; .github/workflows/app.yml
# sends it with these exported:
#   image           the image to run, e.g. crdndwithincsiqze.azurecr.io/dndwithin:<sha>
#   bundle          base64 tar.gz of the compose files, Caddyfile and scripts/
#   backup_account  the storage account backups go to
set -euo pipefail
: "${image:?}" "${bundle:?}" "${backup_account:?}"
export HOME=/root # run-command starts with an almost empty environment; az needs HOME
cd /opt/dnd-within

# Caddy only reads its Caddyfile at start, and `up` won't restart it for a file change.
caddyfile_before=$(sha256sum Caddyfile 2>/dev/null || true)
echo "$bundle" | base64 -d | tar -xz
chown -R azureuser: docker-compose.yml docker-compose.prod.yml Caddyfile scripts

set_env() {
    if grep -q "^$1=" .env; then
        sed -i "s#^$1=.*#$1=$2#" .env
    else
        echo "$1=$2" >> .env
    fi
}
set_env BACKUP_ACCOUNT "$backup_account"

# The schedule ships with the code, so a rebuilt VM gets it on its first deploy.
cp scripts/systemd/dnd-within-backup.service scripts/systemd/dnd-within-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dnd-within-backup.timer

az login --identity --allow-no-subscriptions --output none
az acr login --name "${image%%.*}"

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
# The new image may migrate the schema, and migrations only go forward. Skipped on a fresh VM.
if [ -n "$("${compose[@]}" ps --status running --quiet db)" ]; then
    scripts/backup.sh
fi
# The new image goes in through the environment (which beats .env), so if it never gets healthy
# .env still names the last good one to roll back to. Migrations it ran aren't undone.
APP_IMAGE=$image "${compose[@]}" pull --quiet
if ! APP_IMAGE=$image "${compose[@]}" up -d --remove-orphans --wait --wait-timeout 180; then
    echo "Unhealthy: rolling back to the image in .env"
    "${compose[@]}" up -d --remove-orphans --wait --wait-timeout 180 || true
    exit 1
fi

# Only now, so backup.sh, restore-db.sh and the next rollback use an image that worked.
set_env APP_IMAGE "$image"
# A restart, not `caddy reload`: tar replaced the file, and the running container still
# sees the old one through its bind mount.
if [ "$(sha256sum Caddyfile)" != "$caddyfile_before" ]; then
    "${compose[@]}" restart caddy
fi
docker image prune -f
"${compose[@]}" ps
echo "Deploy succeeded: $image"

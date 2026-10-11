#!/usr/bin/env bash
# Runs on the VM as root with bash, through az vm run-command; .github/workflows/app.yml
# sends it with these exported:
#   image   the image to run, e.g. crdndwithincsiqze.azurecr.io/dndwithin:<sha>
#   bundle  base64 tar.gz of the compose files, Caddyfile and scripts/
set -euo pipefail
export HOME=/root # run-command starts with an almost empty environment; az needs HOME
cd /opt/dnd-within

# Caddy only reads its Caddyfile at start, and `up` won't restart it for a file change.
caddyfile_before=$(sha256sum Caddyfile 2>/dev/null || true)
echo "${bundle:?}" | base64 -d | tar -xz
chown -R azureuser: docker-compose.yml docker-compose.prod.yml Caddyfile scripts

# Record the image in .env, so backup.sh and restore-db.sh run against the deployed one.
if grep -q '^APP_IMAGE=' .env; then
    sed -i "s#^APP_IMAGE=.*#APP_IMAGE=${image:?}#" .env
else
    echo "APP_IMAGE=$image" >> .env
fi

az login --identity --allow-no-subscriptions --output none
az acr login --name "${image%%.*}"

compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
"${compose[@]}" pull --quiet
"${compose[@]}" up -d --remove-orphans
# A restart, not `caddy reload`: tar replaced the file, and the running container still
# sees the old one through its bind mount.
if [ "$(sha256sum Caddyfile)" != "$caddyfile_before" ]; then
    "${compose[@]}" restart caddy
fi
docker image prune -f
"${compose[@]}" ps
echo "Deploy succeeded: $image"

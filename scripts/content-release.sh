#!/usr/bin/env bash
# Install a content release from the content-releases container and import it (run on the server):
#   scripts/content-release.sh v1.0.0            # import the packs whose files changed
#   scripts/content-release.sh v1.0.0 --force    # re-import every pack
# The previous packs stay in content-private.old until the next install. Rolling back is
# installing the previous tag: the importer restores rows a newer release retired.
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:?usage: scripts/content-release.sh <tag> [--force]}"
shift
compose=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

tarball=$(mktemp)
trap 'rm -f "$tarball"' EXIT
account=$(sed -n 's/^BACKUP_ACCOUNT=//p' .env)
az login --identity --allow-no-subscriptions --output none
az storage blob download --auth-mode login --account-name "${account:?BACKUP_ACCOUNT missing from .env}" \
    --container-name content-releases --name "$tag.tar.gz" --file "$tarball" --only-show-errors --output none

rm -rf content-private.new
mkdir content-private.new
tar -xzf "$tarball" -C content-private.new
# Checked before the swap, so a release the running image rejects never replaces the current packs.
# A second path, because the service already mounts content-private at /app/content-private.
"${compose[@]}" run --rm --no-deps -T -v "$PWD/content-private.new:/app/content-new:ro" \
    -e CONTENT_PATHS=content-new app python -m app.content check

rm -rf content-private.old
if [ -d content-private ]; then
    mv content-private content-private.old
fi
mv content-private.new content-private
"${compose[@]}" run --rm --no-deps -T app python -m app.content import "$@"
# Only after the import succeeded, so it names what the database holds.
echo "$tag" > content-private/.release
echo "Installed content release $tag"

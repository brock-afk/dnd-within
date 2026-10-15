#!/usr/bin/env bash
# Runs a script on the app VM through az vm run-command, from a workflow logged in to Azure:
#   .github/scripts/vm-run.sh <script file> <success marker>
# run-command reports success whatever the script's exit code, so the script prints the marker
# only when every step succeeded, and its absence fails this.
set -euo pipefail
result=$(az vm run-command invoke -g rg-dndwithin-iaas -n vm-dndwithin-app \
    --command-id RunShellScript --scripts @"$1" --query "value[0].message" -o tsv)
echo "$result"
grep -q "^$2" <<< "$result"

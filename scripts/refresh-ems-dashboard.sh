#!/bin/bash
# Short offline read job, no Docker, network, server, optimizer or source writes.
set -euo pipefail
umask 077
if [ "$#" -ne 4 ]; then
  printf '%s\n' 'Usage: refresh-ems-dashboard.sh BUNDLE SHA256 READ_ONLY_OUTPUT PRIVATE_DASHBOARD_DIR' >&2
  exit 2
fi
bundle=$1
sha=$2
source_dir=$3
dashboard_dir=$4
[[ "$sha" =~ ^[0-9a-f]{64}$ ]] || exit 2
[ -f "$bundle" ] && [ ! -L "$bundle" ] || exit 2
printf '%s  %s\n' "$sha" "$bundle" | sha256sum -c - >&2
export PYTHONDONTWRITEBYTECODE=1
exec python3 -I -B "$bundle" --source "$source_dir" --destination "$dashboard_dir"

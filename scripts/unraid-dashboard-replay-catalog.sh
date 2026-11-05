#!/bin/bash
# Snapshot one generation; unchanged HTML publisher validates. No replay execution.
set -euo pipefail
umask 077
[ "$#" -eq 4 ] || { printf '%s\n' 'Usage: unraid-dashboard-replay-catalog.sh TOOLS PRIVATE PUBLISH REPLAYS' >&2; exit 2; }
tools=$1; work=$2; publish=$3; replays=$4
for directory in "$tools" "$work" "$publish" "$replays"; do
  [ -d "$directory" ] && [ ! -L "$directory" ] || exit 2
done
catalog="$replays/catalog.json"
snapshot=''
cleanup() { if [ -n "$snapshot" ]; then rm -f -- "$snapshot"; fi; }
trap cleanup EXIT
if [ ! -e "$catalog" ] && [ ! -L "$catalog" ]; then
  bash "$tools/unraid-dashboard-publish.sh" "$tools" "$work" "$publish"
  exit $?
fi
[ -f "$catalog" ] && [ ! -L "$catalog" ] || exit 2
# One open pins the inode across atomic catalog replacements.
exec 7<"$catalog"
size=$(stat -Lc %s /proc/self/fd/7)
[ "$size" -gt 0 ] && [ "$size" -le 32000000 ] || exit 2
snapshot=$(mktemp "$work/.replay-catalog-XXXXXXXX")
cat <&7 > "$snapshot"
[ "$(stat -c %s -- "$snapshot")" -eq "$size" ] || exit 2
bash "$tools/unraid-dashboard-publish.sh" "$tools" "$work" "$publish" --replays "$snapshot"

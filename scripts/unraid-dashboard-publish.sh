#!/bin/bash
# Pure HTML read-export. No replay, optimizer, helper reconfiguration or deployment.
set -euo pipefail
umask 077
usage() { printf '%s\n' 'Usage: unraid-dashboard-publish.sh TOOLS PRIVATE_WORK PUBLISH [--replays SIDECAR]' >&2; exit 2; }
[ "$#" -eq 3 ] || [ "$#" -eq 5 ] || usage
tools=$1; work=$2; publish=$3
shift 3
replays=()
if [ "$#" -gt 0 ]; then
  [ "$1" = --replays ] && [ -f "$2" ] && [ ! -L "$2" ] || usage
  replays=(--replays "$2")
fi
for directory in "$tools" "$work" "$publish"; do
  [ -d "$directory" ] && [ ! -L "$directory" ] || usage
done
tools=$(readlink -f -- "$tools")
work=$(readlink -f -- "$work")
publish=$(readlink -f -- "$publish")
disjoint() {
  [ "$1" != / ] && [ "$2" != / ] || return 1
  case "$1/" in "$2/"*) return 1 ;; esac
  case "$2/" in "$1/"*) return 1 ;; esac
}
disjoint "$tools" "$work" && disjoint "$tools" "$publish" && disjoint "$work" "$publish" || usage
# Discover the same helper as the pinned reader, before ANY write/lock creation.
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
helper=''; count=0
ids=$(docker ps --quiet --no-trunc)
while IFS= read -r id; do
  [ -n "$id" ] || continue
  [[ "$id" =~ ^[0-9a-f]{12,64}$ ]] || exit 1
  identity=$(docker inspect --format '{{.State.Running}} {{.Config.Image}}' "$id")
  if [[ "$identity" =~ ^true\ ghcr[.]io/vbeinlich/eospvprognosehelfer(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(@sha256:[0-9a-f]{64})?$ ]]; then
    count=$((count+1)); helper=$id
  fi
done <<< "$ids"
[ "$count" -eq 1 ] || { printf '%s\n' 'Exactly one existing helper required; no deployment attempted' >&2; exit 1; }
source_dir=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/output"}}{{println .Source}}{{end}}{{end}}' "$helper")
[ -n "$source_dir" ] && [ -d "$source_dir" ] || exit 1
source_dir=$(readlink -f -- "$source_dir")
for directory in "$tools" "$work" "$publish"; do
  disjoint "$directory" "$source_dir" || { printf '%s\n' 'Publication paths overlap EMS output; refusing all writes' >&2; exit 2; }
done
for file in "$work/.publish.lock" "$work/index.html" "$publish/index.html"; do
  [ ! -L "$file" ] || usage
done
exec 8>"$work/.publish.lock"
flock -n 8 || { printf '%s\n' 'Another HTML export is running; skipped' >&2; exit 0; }
tmp=''
cleanup() { if [ -n "$tmp" ]; then rm -f -- "$tmp"; fi; }
trap cleanup EXIT
complete() {
  [ -f "$1" ] && [ ! -L "$1" ] &&
    head -c 15 "$1" | cmp -s - <(printf '<!doctype html>') &&
    tail -c 14 "$1" | cmp -s - <(printf '</body></html>') &&
    grep -q 'id="transport-error"' "$1"
}
atomic_publish() {
  tmp=$(mktemp "$publish/.publish-XXXXXXXX")
  cat -- "$1" > "$tmp"
  sync -f "$tmp"
  chmod 0644 "$tmp"
  mv -f -- "$tmp" "$publish/index.html"
  tmp=''
  sync -f "$publish"
}
mark_error() {
  if complete "$publish/index.html"; then
    tmp=$(mktemp "$publish/.publish-XXXXXXXX")
    sed 's/id="transport-error" hidden/id="transport-error"/' "$publish/index.html" > "$tmp"
    sync -f "$tmp"
    chmod 0644 "$tmp"
    mv -f -- "$tmp" "$publish/index.html"
    tmp=''
    sync -f "$publish"
  fi
  printf '%s\n' 'HTML export failed; last valid publication retained with visible update warning' >&2
}
bundle="$tools/ems-dashboard-final.pyz"
wrapper="$tools/unraid-ems-dashboard.sh"
bundle_sha=ec2666b596700595c34a1aeef058dda1edb0db713e0811451435c87038b2846c
wrapper_sha=312a9f748cf5e928eb665769b057ddfdb64005ce91707b16ad1ef8a13782f04e
status=0
if [ ! -f "$bundle" ] || [ -L "$bundle" ] || [ ! -f "$wrapper" ] || [ -L "$wrapper" ] ||
   ! printf '%s  %s\n%s  %s\n' "$bundle_sha" "$bundle" "$wrapper_sha" "$wrapper" | sha256sum -c - >&2; then
  mark_error; exit 1
fi
# Seed the reader's private last-good cache after a private work-directory loss.
if [ ! -e "$work/index.html" ] && complete "$publish/index.html"; then
  tmp=$(mktemp "$work/.seed-XXXXXXXX")
  cat -- "$publish/index.html" > "$tmp"
  sync -f "$tmp"
  mv -f -- "$tmp" "$work/index.html"
  tmp=''
fi
bash "$wrapper" "$bundle" "$bundle_sha" "$work" "${replays[@]}" || status=$?
if { [ "$status" -eq 0 ] || [ "$status" -eq 2 ]; } && complete "$work/index.html"; then
  atomic_publish "$work/index.html"
  exit "$status"
fi
mark_error
exit 1

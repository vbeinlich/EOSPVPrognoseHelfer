#!/bin/bash
# Separate operator-approved schedule only; never called by HTML refresh.
set -euo pipefail
umask 077
usage() { printf '%s\n' 'Usage: unraid-native-replay-worker.sh IMMUTABLE_IMAGE ORIGINAL_OUTPUT PRIVATE_REPLAYS [--version VERSION]' >&2; exit 2; }
[ "$#" -eq 3 ] || [ "$#" -eq 5 ] || usage
image=$1; source=$2; work=$3
shift 3
[[ "$image" =~ ^sha256:[0-9a-f]{64}$ || "$image" =~ ^[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}$ ]] || usage
args=()
if [ "$#" -gt 0 ]; then
  [ "$1" = --version ] && [[ "$2" =~ ^[0-9a-f]{64}$ ]] || usage
  args=(--version "$2")
fi
for folder in "$source" "$work"; do
  [ -d "$folder" ] && [ ! -L "$folder" ] || usage
done
source=$(readlink -f -- "$source"); work=$(readlink -f -- "$work")
[ "$source" != / ] && [ "$work" != / ] || usage
case "$source/" in "$work/"*) usage ;; esac
case "$work/" in "$source/"*) usage ;; esac
# No credentials, devices, privileged mode, host networking or helper exec.
exec timeout --signal=TERM --kill-after=10s 125s \
  docker --host unix:///var/run/docker.sock run --rm --pull=never \
  --network none --read-only --user 10001:10001 --cap-drop=ALL \
  --security-opt=no-new-privileges --cpus=0.50 --cpu-shares=64 \
  --memory=768m --memory-swap=768m --pids-limit=128 --blkio-weight=100 \
  --ulimit nofile=1024:1024 --ulimit core=0:0 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --mount "type=bind,source=$source,target=/archive,readonly" \
  --mount "type=bind,source=$work,target=/replays" \
  "$image" --settle-seconds 2 --timeout 90 --cpu-seconds 30 \
  --address-space-mb 3072 "${args[@]}"

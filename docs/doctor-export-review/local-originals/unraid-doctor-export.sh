#!/bin/bash
# Operator-only: run in the Unraid terminal. Reads the existing helper only.
# Creates a NEW private diagnostic directory under /tmp, never changes appdata.
set -euo pipefail
umask 077
set -C

# Always use Unraid's local Docker socket; do not follow a remote context.
docker() { command docker --host unix:///var/run/docker.sock "$@"; }

accept_dir=$(mktemp -d /tmp/eos-v010-doctor.XXXXXXXX)
source_revision=47bd42468ffbf2876143ba950512e968825a5f53
script_sha256=56a950467d27482bf3361c0739f6cccab394dcbe04d3c0238255119d6bbc8ca5

# Select exactly one RUNNING helper from its configured GHCR image, not its name.
helper_id=$(docker ps --format '{{.ID}} {{.Image}}' | awk '$2 ~ /^ghcr.io\/vbeinlich\/eospvprognosehelfer[:@]/ {print $1}')
case "$helper_id" in
  ''|*[!0-9a-f]*)
    printf '%s\n' 'STOP: could not identify exactly one running helper. Do not start/stop a container.' >&2
    exit 1
    ;;
esac

# Refuse unexpected/missing mount destinations; never guess alternative paths.
mount_destinations=$(docker inspect --format '{{range .Mounts}}{{println .Destination}}{{end}}' "$helper_id")
printf '%s\n' "$mount_destinations" | awk '$0=="/output" {found=1} END {exit !found}'
printf '%s\n' "$mount_destinations" | awk '$0=="/app/config.toml" {found=1} END {exit !found}'

# Pin the already reviewed exporter. No install/update inside the helper.
curl --fail --silent --show-error --location \
  "https://raw.githubusercontent.com/vbeinlich/EOSPVPrognoseHelfer/$source_revision/scripts/doctor_snapshot.py" \
  --output "$accept_dir/doctor_snapshot.py"
printf '%s  %s\n' "$script_sha256" "$accept_dir/doctor_snapshot.py" | sha256sum -c - > "$accept_dir/script-check.txt"

# Provenance without full inspect, environment variables, config or secret dumps.
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$accept_dir/operator-observed-at-utc.txt"
printf '%s\n' "$source_revision" > "$accept_dir/exporter-source-revision.txt"
docker inspect --format '{"container_id":{{json .Id}},"name":{{json .Name}},"configured_image":{{json .Config.Image}},"image_id":{{json .Image}}}' \
  "$helper_id" > "$accept_dir/runtime.json"
image_id=$(docker inspect --format '{{.Image}}' "$helper_id")
docker image inspect --format '{"source":{{json (index .Config.Labels "org.opencontainers.image.source")}},"revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}},"version":{{json (index .Config.Labels "org.opencontainers.image.version")}}}' \
  "$image_id" > "$accept_dir/image-origin.json"

# Shared-lock export; reads only four existing artifacts plus validation limits.
# No POST, import, refresh, simulation, configuration update or claim reset.
# If a normal sync holds the lock or no matching event exists, abort and retry
# later using a fresh directory; do not trigger a sync/optimization manually.
docker exec -i "$helper_id" python - --source /output --config /app/config.toml \
  < "$accept_dir/doctor_snapshot.py" > "$accept_dir/doctor-snapshot.zip"
sha256sum "$accept_dir/doctor_snapshot.py" "$accept_dir/doctor-snapshot.zip" \
  > "$accept_dir/SHA256SUMS.txt"
printf 'Export successful; private directory: %s\n' "$accept_dir"
printf '%s\n' 'Keep ALL files private. Transfer securely to the diagnosis computer, never to GitHub.'
printf '%s\n' 'This is an export, not Doctor acceptance. Validate offline; never backdate timestamps.'

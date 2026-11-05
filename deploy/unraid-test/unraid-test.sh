#!/bin/bash
# PREPARED ONLY: manually run on Unraid. Never resets output, claims or solutions.
set -Eeuo pipefail
umask 077
package=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
usage() { printf '%s\n' 'Usage: unraid-test.sh install | rollback BACKUP | check-archive BACKUP | start-worker BACKUP HISTORICAL_SIDECAR_OR_none | publisher-test BACKUP | publisher-command BACKUP' >&2; exit 2; }
[ "$#" -ge 1 ] || usage
action=$1; shift
[ "$(id -u)" -eq 0 ] || { printf '%s\n' 'Run from the Unraid root terminal.' >&2; exit 2; }
cd -- "$package"
sha256sum --quiet -c SHA256SUMS
# This file contains ONLY reviewed local tags, IDs and TAR names; checksum checked above.
source "$package/images.env"
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
exec 8>/var/lock/ems-v11-test-install.lock
flock -n 8 || { printf '%s\n' 'Another migration command is active.' >&2; exit 2; }
backup=''; switched=0; changed=0; stopped=0; new_id=''
read_plan() {
  [ -d "$backup" ] && [ ! -L "$backup" ] && [ -f "$backup/plan-lines" ] || usage
  [ "$(stat -c %u:%a -- "$backup")" = 0:700 ] || usage
  for master in plan-lines old-name config-original.toml config-enabled.toml container-inspect.json; do
    [ -f "$backup/$master" ] && [ ! -L "$backup/$master" ] &&
      [ "$(stat -c %u:%a -- "$backup/$master")" = 0:600 ] || usage
  done
  mapfile -t plan < "$backup/plan-lines"
  [ "${#plan[@]}" -eq 6 ] || usage
  old_id=${plan[0]}; old_image=${plan[1]}; config=${plan[2]}; output=${plan[3]}; config_sha=${plan[4]}; wait_seconds=${plan[5]}
  [[ "$old_id" =~ ^[0-9a-f]{64}$ && "$old_image" =~ ^sha256:[0-9a-f]{64}$ && "$config_sha" =~ ^[0-9a-f]{64}$ && "$wait_seconds" =~ ^[0-9]+$ ]] || usage
  [ -f "$config" ] && [ ! -L "$config" ] && [ -d "$output" ] && [ ! -L "$output" ] || usage
  old_name=$(cat -- "$backup/old-name")
  [[ "$old_name" =~ ^eos-pv-helper-before-[0-9TZ-]+$ ]] || usage
}
matches_image() {
  # Docker classic uses config IDs; containerd may expose its local manifest ID.
  local value
  value=$(docker image inspect --format '{{.Id}}' "$1")
  [ "$value" = "$2" ] || [ "$value" = "$3" ]
}
safe_stop() {
  local target=$1
  [ "$(docker inspect --format '{{.State.Running}}' "$target")" = true ] || return 0
  [ -f "$output/sync.lock" ] && [ ! -L "$output/sync.lock" ] || { printf '%s\n' 'Existing sync lock missing; refusing a forced stop.' >&2; return 1; }
  # Signal only while the original tick/dispatch lock is free. TERM is caught by
  # the helper; NEVER docker stop's timed SIGKILL and never kill a running POST.
  exec 9<"$output/sync.lock" || return 1
  if ! flock -x -w "$wait_seconds" 9; then exec 9<&-; return 1; fi
  if [ -L "$output/sync.lock" ] ||
     [ "$(stat -Lc %d:%i /proc/self/fd/9)" != "$(stat -c %d:%i -- "$output/sync.lock")" ]; then
    flock -u 9; exec 9<&-; return 1
  fi
  if ! docker kill --signal TERM "$target" >/dev/null; then
    flock -u 9; exec 9<&-; return 1
  fi
  flock -u 9 || return 1
  exec 9<&-
  timeout "$wait_seconds" docker --host unix:///var/run/docker.sock wait "$target" >/dev/null || return 1
  [ "$(docker inspect --format '{{.State.Running}}' "$target")" = false ]
}
atomic_config() {
  local source=$1 temporary
  temporary=$(mktemp "$(dirname -- "$config")/.ems-config-XXXXXXXX") || return 1
  if ! cp --preserve=mode,ownership -- "$config" "$temporary" ||
     ! cat -- "$source" > "$temporary" || ! sync -f "$temporary"; then
    rm -f -- "$temporary"; return 1
  fi
  if ! mv -f -- "$temporary" "$config"; then rm -f -- "$temporary"; return 1; fi
  sync -f "$(dirname -- "$config")"
}
restore() {
  # Stop only our replacement. Keep every original output/state byte in place.
  local current
  [ "$(docker inspect --format '{{.Id}}' "$old_id")" = "$old_id" ] || return 1
  if [ "${1:-1}" = 1 ]; then
    local digest original enabled
    digest=$(sha256sum -- "$config"); digest=${digest%% *}
    original=$(sha256sum -- "$backup/config-original.toml"); original=${original%% *}
    enabled=$(sha256sum -- "$backup/config-enabled.toml"); enabled=${enabled%% *}
    [ "$digest" = "$original" ] || [ "$digest" = "$enabled" ] || { printf '%s\n' 'Configuration changed since migration; refusing to overwrite it.' >&2; return 1; }
  fi
  current=$(docker inspect --format '{{.Id}}' eos-pv-helper 2>/dev/null || true)
  if [ -n "$current" ] && [ "$current" != "$old_id" ]; then
    if [ -f "$backup/new-id" ]; then
      [ "$current" = "$(cat -- "$backup/new-id")" ] || return 1
    else
      [ "$(docker inspect --format '{{index .Config.Labels "org.eos.test.original-container"}}' "$current")" = "$old_id" ] || return 1
      [ "$(docker inspect --format '{{.Config.Image}}' "$current")" = "$HELPER_TAG" ] || return 1
    fi
    safe_stop "$current" || return 1
    docker rm "$current" >/dev/null || return 1
  fi
  if [ "${1:-1}" = 1 ] && [ -f "$backup/config-enabled.toml" ]; then
    atomic_config "$backup/config-original.toml" || return 1
  fi
  [ "$(docker inspect --format '{{.Id}}' "$old_id")" = "$old_id" ] || return 1
  if [ "$(docker inspect --format '{{.Name}}' "$old_id")" != /eos-pv-helper ]; then
    docker rename "$old_id" eos-pv-helper || return 1
  fi
  [ "$(docker inspect --format '{{.State.Running}}' "$old_id")" = true ] || docker start "$old_id" >/dev/null || return 1
  printf '%s\n' 'Original helper restored. Claims, solutions, archives and replay data were NOT reset.'
}
on_error() {
  trap - ERR
  if [ "$changed" -eq 1 ] || [ "$switched" -eq 1 ] || [ "$stopped" -eq 1 ]; then
    printf '%s\n' 'Migration failed; attempting controlled rollback.' >&2
    restore "$changed" || printf '%s\n' "Rollback could not safely finish. Do not start a second helper. Backup: $backup" >&2
  fi
  exit 1
}
prepare_review_input() {
  # Root-owned master backup/plan remains mode 0700/0600. Expose ONLY these
  # non-secret reference copies to non-root offline readers via a read-only bind.
  view="$backup/review-input"
  [ ! -L "$view" ]
  if [ ! -d "$view" ]; then mkdir -m 0700 -- "$view"; fi
  for name in claims-before.json installed-at-utc archive-accepted.json; do
    if [ -f "$backup/$name" ]; then
      cp -- "$backup/$name" "$view/$name"
      chmod 0400 -- "$view/$name"
      chown 10001:10001 -- "$view/$name"
    fi
  done
  chown 10001:10001 -- "$view"
}
offline() {
  local image=$1 mode=$2
  prepare_review_input
  # A short review process must not look like a second ghcr-tagged live helper
  # to the existing publisher. The actual helper keeps its reviewed local tag.
  image=$(docker image inspect --format '{{.Id}}' "$image")
  docker run --rm --pull=never --network none --read-only --user 10001:10001 --cap-drop=ALL \
    --security-opt=no-new-privileges --cpus=.5 --memory=768m --memory-swap=768m --pids-limit=128 \
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
    --mount "type=bind,source=$output,target=/archive,readonly" \
    --mount "type=bind,source=$view,target=/migration,readonly" \
    --mount "type=bind,source=$package/tools/verify.py,target=/review/verify.py,readonly" \
    "${offline_extra[@]}" --entrypoint python "$image" /review/verify.py "$mode"
}
worker_args() {
  worker_flags=(--pull=never --network none --read-only --user 10001:10001 --cap-drop=ALL
    --security-opt=no-new-privileges --cpus=.5 --cpu-shares=64 --memory=768m --memory-swap=768m
    --pids-limit=128 --ulimit core=0:0 --ulimit nofile=1024:1024
    --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777
    --mount "type=bind,source=$output,target=/archive,readonly"
    --mount "type=bind,source=$workspace,target=/replays")
}
if [ "$action" = install ]; then
  [ "$#" -eq 0 ] || usage
  for tool in curl flock timeout sha256sum tar sync; do command -v "$tool" >/dev/null; done
  rollback_tar=/mnt/user/appdata/ems-dashboard-review/backup/eos-pv-helper-rollback-e1c47a73.tar
  printf '%s  %s\n' "$ROLLBACK_SHA256" "$rollback_tar" | sha256sum -c -
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  backup="/mnt/user/appdata/ems-dashboard-review/backup/ems-v11-$stamp"
  mkdir -m 0700 -- "$backup"
  chmod 0700 -- "$backup"
  docker inspect eos-pv-helper > "$backup/container-inspect-before.json"
  old_id=$(docker inspect --format '{{.Id}}' eos-pv-helper)
  old_image=$(docker inspect --format '{{.Image}}' "$old_id")
  [ "$old_image" = sha256:e1c47a73e80272fd4fae9653d02ff9b993e894b4e6d39495e49b6fbd93f3495d ] || { printf '%s\n' 'Active helper differs from the operator-confirmed image. Nothing replaced.' >&2; exit 1; }
  old_name="eos-pv-helper-before-$stamp"
  printf '%s\n' "$old_name" > "$backup/old-name"
  docker exec -i "$old_id" python -B -c "$(cat -- "$package/tools/prepare.py")" "$HELPER_TAG" \
    < "$backup/container-inspect-before.json" > "$backup/config-backup.tar"
  tar -xf "$backup/config-backup.tar" -C "$backup"
  read_plan
  # Only NEW backup files, not any original or previously saved operator backup.
  chmod -R go-rwx -- "$backup"
  docker load -i "$package/$HELPER_TAR" > "$backup/image-load.log"
  matches_image "$HELPER_TAG" "$HELPER_CONFIG_ID" "$HELPER_LOCAL_ID"
  trap on_error ERR
  safe_stop "$old_id"
  stopped=1
  [ "$(sha256sum -- "$config" | cut -d' ' -f1)" = "$config_sha" ]
  changed=1
  atomic_config "$backup/config-enabled.toml"
  docker rename "$old_id" "$old_name"
  switched=1
  api=$(docker version --format '{{.Server.APIVersion}}')
  [[ "$api" =~ ^[0-9]+\.[0-9]+$ ]]
  curl --silent --show-error --fail --noproxy '*' --unix-socket /var/run/docker.sock \
    -H 'Content-Type: application/json' --data-binary "@$backup/container-create.json" \
    "http://localhost/v$api/containers/create?name=eos-pv-helper" > "$backup/create-response.json"
  new_id=$(docker inspect --format '{{.Id}}' eos-pv-helper)
  printf '%s\n' "$new_id" > "$backup/new-id"
  actual_image=$(docker inspect --format '{{.Image}}' "$new_id")
  [ "$actual_image" = "$HELPER_CONFIG_ID" ] || [ "$actual_image" = "$HELPER_LOCAL_ID" ]
  date -u +%Y-%m-%dT%H:%M:%SZ > "$backup/installed-at-utc"
  docker start "$new_id" >/dev/null
  sleep 15
  [ "$(docker inspect --format '{{.State.Running}}' "$new_id")" = true ]
  docker inspect "$new_id" > "$backup/candidate-inspect.json"
  { printf '{"old":'; cat -- "$backup/container-inspect.json"; printf ',"new":'; cat -- "$backup/candidate-inspect.json"; printf '}'; } |
    docker exec -i "$new_id" python -B -c "$(cat -- "$package/tools/verify.py")" runtime > "$backup/startup-check.json"
  trap - ERR
  printf '%s\n' "Helper running; archive proof is still pending. Backup: $backup" \
    "Next: bash '$package/tools/unraid-test.sh' check-archive '$backup'" \
    "Rollback: bash '$package/tools/unraid-test.sh' rollback '$backup'"
  exit 0
fi
[ "$#" -ge 1 ] || usage
backup=$(readlink -f -- "$1"); shift
read_plan
workspace=/mnt/user/appdata/ems-dashboard-review/replays-v11-546baa63
offline_extra=()
case "$action" in
  rollback)
    [ "$#" -eq 0 ] || usage
    if docker inspect ems-native-replay-v11 >/dev/null 2>&1; then
      [ "$(docker inspect --format '{{index .Config.Labels "org.eos.test.package"}}' ems-native-replay-v11)" = ems-v11-546baa63 ]
      docker stop --time 110 ems-native-replay-v11 >/dev/null
    fi
    restore ;;
  check-archive)
    [ "$#" -eq 0 ] || usage
    offline "$HELPER_TAG" archive > "$backup/archive-accepted.json.tmp"
    mv -- "$backup/archive-accepted.json.tmp" "$backup/archive-accepted.json"
    cat -- "$backup/archive-accepted.json" ;;
  start-worker)
    [ "$#" -eq 1 ] && [ -f "$backup/archive-accepted.json" ] || usage
    historical=$1
    docker load -i "$package/$WORKER_TAR" > "$backup/worker-image-load.log"
    matches_image "$WORKER_TAG" "$WORKER_CONFIG_ID" "$WORKER_LOCAL_ID"
    if [ ! -e "$workspace" ]; then mkdir -m 0700 -- "$workspace"; chown 10001:10001 -- "$workspace"; fi
    [ -d "$workspace" ] && [ ! -L "$workspace" ] && [ "$(stat -c %u:%g:%a -- "$workspace")" = 10001:10001:700 ]
    worker_args
    prepare_review_input
    # Admission starts at the REAL helper activation, including plans archived
    # during the manual archive-test/worker-start gap. Existing state is untouched.
    docker run --rm "${worker_flags[@]}" --mount "type=bind,source=$view,target=/migration,readonly" \
      --mount "type=bind,source=$package/tools/verify.py,target=/review/verify.py,readonly" \
      --entrypoint python "$WORKER_TAG" /review/verify.py init-worker
    if [ "$historical" != none ]; then
      [ -f "$historical" ] && [ ! -L "$historical" ]
      historical=$(readlink -f -- "$historical")
      cp -- "$historical" "$view/legacy-sidecar.json"
      chmod 0400 -- "$view/legacy-sidecar.json"; chown 10001:10001 -- "$view/legacy-sidecar.json"
      docker run --rm "${worker_flags[@]}" --mount "type=bind,source=$view/legacy-sidecar.json,target=/legacy/sidecar.json,readonly" \
        "$WORKER_TAG" --import-sidecar /legacy/sidecar.json
    fi
    version=$(docker run --rm --network none --read-only --user 10001:10001 --cap-drop=ALL --security-opt=no-new-privileges \
      --mount "type=bind,source=$view,target=/migration,readonly" --entrypoint python "$WORKER_TAG" -c \
      'import json;print(json.load(open("/migration/archive-accepted.json"))["version"])')
    [[ "$version" =~ ^[0-9a-f]{64}$ ]]
    # Explicitly select only the NEW post-install version; future plans use the watermark.
    docker run --rm "${worker_flags[@]}" "$WORKER_TAG" --version "$version"
    sleep 3
    docker run --rm "${worker_flags[@]}" "$WORKER_TAG" --version "$version"
    offline_extra=(--mount "type=bind,source=$workspace,target=/replays,readonly")
    offline "$WORKER_TAG" worker > "$backup/worker-accepted.json"
    # Never replace an existing container silently.
    if docker inspect ems-native-replay-v11 >/dev/null 2>&1; then
      [ "$(docker inspect --format '{{index .Config.Labels "org.eos.test.package"}}' ems-native-replay-v11)" = ems-v11-546baa63 ]
      [ "$(docker inspect --format '{{.Config.Image}}' ems-native-replay-v11)" = "$WORKER_TAG" ]
      [ "$(docker inspect --format '{{.State.Running}}' ems-native-replay-v11)" = true ] || docker start ems-native-replay-v11 >/dev/null
    else
      docker run -d --name ems-native-replay-v11 --restart no --label org.eos.test.package=ems-v11-546baa63 \
        --log-opt max-size=1m --log-opt max-file=2 \
        "${worker_flags[@]}" "$WORKER_TAG" --watch --poll-seconds 60 >/dev/null
    fi
    cat -- "$backup/worker-accepted.json" ;;
  publisher-test|publisher-command)
    [ "$#" -eq 0 ] && [ -f "$backup/worker-accepted.json" ]
    args=("$package/tools" /mnt/user/appdata/ems-dashboard-review/private /mnt/user/appdata/ems-dashboard-review/publish "$workspace")
    if [ "$action" = publisher-test ]; then
      bash "$package/tools/unraid-dashboard-replay-catalog.sh" "${args[@]}"
    else
      printf 'bash %q' "$package/tools/unraid-dashboard-replay-catalog.sh"
      printf ' %q' "${args[@]}"
      printf '\n'
    fi ;;
  *) usage ;;
esac

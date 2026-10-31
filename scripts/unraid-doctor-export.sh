#!/bin/bash
# Operator-only: run in the Unraid terminal. Reads the existing helper only.
# --check-only creates no files; --export creates a NEW private /tmp directory.
set -euo pipefail
umask 077
set -C

# Always use Unraid's local Docker socket; do not follow a remote context.
docker() { command docker --host unix:///var/run/docker.sock "$@"; }

mode=${1:---check-only}
if [ "$#" -gt 1 ] || { [ "$mode" != '--export' ] && [ "$mode" != '--check-only' ]; }; then
  printf '%s\n' 'Usage: bash unraid-doctor-export.sh [--check-only|--export]' >&2
  exit 2
fi
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

# A point-in-time read-only preflight. Export acquires its own lock again later.
if [ "$mode" = '--check-only' ]; then
  preflight=$(cat <<'PY'
import fcntl, json, re, sys, tomllib
from pathlib import Path
try:
    root, config = Path(sys.argv[1]), Path(sys.argv[2])
    lock = root / 'sync.lock'
    if lock.is_symlink() or not lock.is_file():
        raise ValueError()
    with lock.open('rb') as handle:
        fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        def read(name):
            path = root / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 8_000_000:
                raise ValueError()
            with path.open('rb') as source:
                raw = source.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ValueError()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        report = read('sync-report.json')
        version = report.get('event', {}).get('version', '')
        if not re.fullmatch('[0-9a-f]{64}', version):
            raise ValueError()
        state = read('sync-state.json')
        if state.get('events', {}).get(version, {}).get('status') != 'succeeded':
            raise ValueError()
        read('prices.json')
        read('solution-' + version + '.json')
        with config.open('rb') as settings:
            tomllib.load(settings)
except Exception:
    raise SystemExit('Read-only preflight blocked; check files, configuration or active sync locally') from None
print(json.dumps({'preflight': 'passed', 'read_only': True, 'shared_lock_verified': True,
                  'artifact_count': 4, 'export_created': False, 'doctor_acceptance': False}))
PY
)
  docker exec -i "$helper_id" python -c "$preflight" /output /app/config.toml
  exit 0
fi

accept_dir=$(mktemp -d /tmp/eos-v010-doctor.XXXXXXXX)
# Pin the already reviewed exporter. No install/update inside the helper.
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 60 \
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

# Validate in memory before emitting any ZIP bytes to the private output file.
# This is an integrity/privacy check, NOT a Doctor acceptance or live measurement.
zip_guard=$(cat <<'PY'
import hashlib, io, json, re, sys, zipfile
try:
    raw = sys.stdin.buffer.read(40_000_001)
    if len(raw) > 40_000_000:
        raise ValueError()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) != 5 or len({i.filename for i in infos}) != 5 or any(i.file_size > 8_000_000 for i in infos):
            raise ValueError()
        manifest = json.loads(archive.read('snapshot.json'))
        version = manifest['event_version']
        if not re.fullmatch('[0-9a-f]{64}', version) or manifest.get('configured_constraints_read') is not True:
            raise ValueError()
        expected = {'sync-report.json', 'sync-state.json', 'prices.json', 'solution-' + version + '.json'}
        if set(manifest['files']) != expected or {i.filename for i in infos} != expected | {'snapshot.json'}:
            raise ValueError()
        forbidden = {'token', 'accesstoken', 'refreshtoken', 'password', 'passwd', 'secret', 'apikey',
                     'bearertoken', 'authorization', 'cookie', 'clientsecret', 'privatekey', 'config',
                     'configuration', 'tokenfile', 'bearertokenfile', 'headers'}
        credential = re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|Bearer\s+[A-Za-z0-9._-]{12,}')
        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if re.sub('[^a-z]', '', key.lower()) in forbidden:
                        raise ValueError()
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
            elif isinstance(value, str) and credential.search(value):
                raise ValueError()
        check(manifest)
        for name in expected:
            payload = archive.read(name)
            if hashlib.sha256(payload).hexdigest() != manifest['files'][name]:
                raise ValueError()
            check(json.loads(payload))
except Exception:
    raise SystemExit('Private export rejected by integrity/privacy guard; no archive emitted') from None
sys.stdout.buffer.write(raw)
PY
)

# Shared-lock export; reads only four existing artifacts plus validation limits.
# No POST, import, refresh, simulation, configuration update or claim reset.
# If a normal sync holds the lock or no matching event exists, abort and retry
# later using a fresh directory; do not trigger a sync/optimization manually.
docker exec -i "$helper_id" python - --source /output --config /app/config.toml \
  < "$accept_dir/doctor_snapshot.py" \
  | docker exec -i "$helper_id" python -c "$zip_guard" > "$accept_dir/doctor-snapshot.zip.partial"
mv -- "$accept_dir/doctor-snapshot.zip.partial" "$accept_dir/doctor-snapshot.zip"
sha256sum "$accept_dir/doctor_snapshot.py" "$accept_dir/doctor-snapshot.zip" \
  > "$accept_dir/SHA256SUMS.txt"
printf 'Export successful; private directory: %s\n' "$accept_dir"
printf '%s\n' 'Keep ALL files private. Transfer securely to the diagnosis computer, never to GitHub.'
printf '%s\n' 'This is an export, not Doctor acceptance. Validate offline; never backdate timestamps.'

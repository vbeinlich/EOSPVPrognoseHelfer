#!/bin/bash
# Operator tool: no installation, no export of raw files, no source modifications.
# Only complete sanitized HTML/JSON is emitted to stdout. No webserver or port.
set -euo pipefail
umask 077
if [ "$#" -lt 2 ]; then
  printf '%s\n' 'Usage: unraid-plan-inspector.sh CODE_BUNDLE SHA256 [--json] [--legacy-timezone Europe/Berlin]' >&2
  exit 2
fi
bundle=$1
bundle_sha=$2
shift 2
format=html
legacy=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --json) format=json; shift ;;
    --comparison-inputs) format=comparison-inputs; shift ;;
    --legacy-timezone)
      [ "$#" -ge 2 ] && [ -z "$legacy" ] || exit 2
      legacy=$2; shift 2 ;;
    *) printf '%s\n' 'Unknown option; no Docker access performed' >&2; exit 2 ;;
  esac
done
[[ "$bundle_sha" =~ ^[0-9a-f]{64}$ ]] || exit 2
if [ -L "$bundle" ] || [ ! -f "$bundle" ]; then
  printf '%s\n' 'Code bundle missing or unsafe' >&2; exit 1
fi
printf '%s  %s\n' "$bundle_sha" "$bundle" | sha256sum -c - >&2
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
ids=$(docker ps --quiet --no-trunc)
count=0
helper=''
pattern='^true ghcr[.]io/vbeinlich/eospvprognosehelfer(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(@sha256:[0-9a-f]{64})?$'
while IFS= read -r id; do
  [ -n "$id" ] || continue
  [[ "$id" =~ ^[0-9a-f]{12,64}$ ]] || exit 1
  identity=$(docker inspect --format '{{.State.Running}} {{.Config.Image}}' "$id")
  if [[ "$identity" =~ $pattern ]]; then count=$((count+1)); helper=$id; fi
done <<< "$ids"
if [ "$count" -ne 1 ]; then
  printf '%s\n' 'Exactly one running helper is required; no start/stop/configuration changes performed' >&2
  exit 1
fi
mounts=$(docker inspect --format '{{range .Mounts}}{{println .Destination}}{{end}}' "$helper")
printf '%s\n' "$mounts" | awk '$0=="/output" {found=1} END {exit !found}'
bootstrap=$(cat <<'PY_BOOT'
import hashlib, io, json, sys, types, zipfile
try:
    raw = sys.stdin.buffer.read(1_000_001)
    if len(raw) > 1_000_000 or hashlib.sha256(raw).hexdigest() != sys.argv[1]:
        raise ValueError()
    expected = {'__main__.py', 'plan_inspector.py', 'plan_view.py', 'historical_validator.py', 'economics.py', 'economics_native.py'}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if (len(infos) != 7 or len({i.filename for i in infos}) != 7
                or any(i.file_size > 250_000 for i in infos)
                or {i.filename for i in infos} != expected | {'bundle.json'}):
            raise ValueError()
        manifest = json.loads(archive.read('bundle.json'))
        if manifest['schema_version'] != 1 or set(manifest['files']) != expected:
            raise ValueError()
        sources = {name: archive.read(name) for name in expected}
        if any(hashlib.sha256(code).hexdigest() != manifest['files'][name] for name, code in sources.items()):
            raise ValueError()
    for name in ('historical_validator', 'economics', 'economics_native', 'plan_view', 'plan_inspector'):
        module = types.ModuleType(name)
        sys.modules[name] = module
        exec(compile(sources[name+'.py'], '<reviewed-code-bundle>', 'exec'), module.__dict__)
    fmt, legacy = sys.argv[2], sys.argv[3]
    sys.argv = ['plan-inspector', '--source', '/output', '--format', fmt]
    if legacy:
        sys.argv += ['--legacy-timezone', legacy]
except Exception:
    raise SystemExit('Invalid or incompatible code bundle; no source files changed') from None
raise SystemExit(sys.modules['plan_inspector'].main())
PY_BOOT
)
docker exec -i "$helper" python -I -S -B -c "$bootstrap" "$bundle_sha" "$format" "$legacy" < "$bundle"

#!/bin/bash
# Unraid host: execute ONLY a short offline reader in the already running helper.
# No extra container, helper loop, optimization, network endpoint or device access.
set -euo pipefail
umask 077
{ [ "$#" -eq 3 ] || [ "$#" -eq 4 ]; } || { printf '%s\n' 'Usage: unraid-ems-dashboard.sh CODE_BUNDLE SHA256 PRIVATE_DASHBOARD_DIR [PRIVATE_ECONOMICS_JSON]' >&2; exit 2; }
bundle=$1
sha=$2
dest=$3
cache=${4:-}
cache_size=0
if [ -n "$cache" ]; then
  [ -f "$cache" ] && [ ! -L "$cache" ] || exit 2
  cache_size=$(stat -c %s -- "$cache")
  [ "$cache_size" -le 32000000 ] || exit 2
fi
[[ "$sha" =~ ^[0-9a-f]{64}$ ]] || exit 2
[ -f "$bundle" ] && [ ! -L "$bundle" ] && [ -d "$dest" ] && [ ! -L "$dest" ] || exit 2
dest=$(readlink -f -- "$dest")
[ "$dest" != / ] || exit 2
[ ! -L "$dest/index.html" ] && [ ! -L "$dest/.refresh.lock" ] || exit 2
printf '%s  %s\n' "$sha" "$bundle" | sha256sum -c - >&2
# Keep Docker access local, as in the existing Inspector operator wrapper.
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
helper=''
count=0
while IFS= read -r id; do
  [ -n "$id" ] || continue
  [[ "$id" =~ ^[0-9a-f]{12,64}$ ]] || exit 1
  identity=$(docker inspect --format '{{.State.Running}} {{.Config.Image}}' "$id")
  if [[ "$identity" =~ ^true\ ghcr[.]io/vbeinlich/eospvprognosehelfer(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(@sha256:[0-9a-f]{64})?$ ]]; then
    count=$((count+1)); helper=$id
  fi
done < <(docker ps --quiet --no-trunc)
[ "$count" -eq 1 ] || { printf '%s\n' 'Exactly one existing helper required; nothing started or stopped' >&2; exit 1; }
source_dir=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/output"}}{{println .Source}}{{end}}{{end}}' "$helper")
[ -n "$source_dir" ] && [ -d "$source_dir" ] || exit 1
source_dir=$(readlink -f -- "$source_dir")
case "$dest/" in "$source_dir/"*) printf '%s\n' 'Dashboard target overlaps source output' >&2; exit 2 ;; esac
case "$source_dir/" in "$dest/"*) printf '%s\n' 'Dashboard target overlaps source output' >&2; exit 2 ;; esac
exec 9>"$dest/.refresh.lock"
flock -n 9 || exit 0
bootstrap=$(cat <<'PY_BOOT'
import hashlib, io, sys, types, zipfile
try:
    size = int(sys.argv[2])
    if not 0 < size <= 1_000_000:
        raise ValueError()
    raw = sys.stdin.buffer.read(size)
    if hashlib.sha256(raw).hexdigest() != sys.argv[1]:
        raise ValueError()
    names = ('historical', 'economics', 'economics_native', 'plan_inspector', 'dashboard_view', 'dashboard')
    expected = {'__main__.py', 'eos_pv_helper/__init__.py'} | {'eos_pv_helper/'+n+'.py' for n in names}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) != len(expected) or {i.filename for i in infos} != expected or any(i.file_size > 300_000 for i in infos):
            raise ValueError()
        sources = {n: archive.read('eos_pv_helper/'+n+'.py') for n in names}
    package = types.ModuleType('eos_pv_helper')
    package.__path__ = []
    sys.modules['eos_pv_helper'] = package
    for name in names:
        module = types.ModuleType('eos_pv_helper.'+name)
        module.__package__ = 'eos_pv_helper'
        sys.modules[module.__name__] = module
        setattr(package, name, module)
        exec(compile(sources[name], '<reviewed-dashboard-code>', 'exec'), module.__dict__)
    cache_size = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    if not 0 <= cache_size <= 32_000_000:
        raise ValueError()
    cached = package.plan_inspector.obj(sys.stdin.buffer.read(cache_size)) if cache_size else None
    previous = sys.stdin.buffer.read(128_000_001)
    if len(previous) > 128_000_000:
        raise ValueError()
    html, valid = package.dashboard.render_refresh('/output', previous.decode('utf-8'), cached=cached)
    sys.stdout.buffer.write(html.encode('utf-8'))
except Exception:
    raise SystemExit('Dashboard reader failed; no input files changed') from None
raise SystemExit(0 if valid else 2)
PY_BOOT
)
size=$(stat -c %s -- "$bundle")
tmp=$(mktemp "$dest/.ems-XXXXXXXX")
trap 'rm -f -- "$tmp"' EXIT
status=0
{ cat -- "$bundle"; if [ -n "$cache" ]; then cat -- "$cache"; fi; if [ -f "$dest/index.html" ]; then cat -- "$dest/index.html"; fi; } |
  timeout 45s docker --host unix:///var/run/docker.sock exec -i "$helper" python -I -S -B -c "$bootstrap" "$sha" "$size" "$cache_size" > "$tmp" || status=$?
if { [ "$status" -eq 0 ] || [ "$status" -eq 2 ]; } &&
   head -c 15 "$tmp" | cmp -s - <(printf '<!doctype html>') &&
   tail -c 14 "$tmp" | cmp -s - <(printf '</body></html>'); then
  sync -f "$tmp"
  mv -f -- "$tmp" "$dest/index.html"
  sync -f "$dest"
  exit "$status"
fi
if [ -f "$dest/index.html" ]; then
  sed 's/id="transport-error" hidden/id="transport-error"/' "$dest/index.html" > "$tmp"
  sync -f "$tmp"
  mv -f -- "$tmp" "$dest/index.html"
  sync -f "$dest"
fi
printf '%s\n' 'Dashboard refresh failed; previous valid view retained' >&2
exit 1

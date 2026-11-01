#!/bin/bash
# Read-only operator tool; only --export creates a NEW private /tmp directory.
set -euo pipefail
umask 077
set -C
docker() { command docker --host unix:///var/run/docker.sock "$@"; }
mode=--check-only
if [ "$#" -gt 0 ]; then mode=$1; shift; fi
if [ "$mode" != '--check-only' ] && [ "$mode" != '--export' ]; then
  printf '%s\n' 'Usage: unraid-doctor-export.sh [--check-only|--export] [--historical-snapshot ZIP] [--event-version SHA256]' >&2
  exit 2
fi
snapshot=''
version=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --historical-snapshot)
      [ "$#" -ge 2 ] && [ -z "$snapshot" ] || exit 2
      snapshot=$2; shift 2 ;;
    --event-version)
      [ "$#" -ge 2 ] && [ -z "$version" ] || exit 2
      version=$2; shift 2 ;;
    *) printf '%s\n' 'Unknown option; no Docker access or export performed' >&2; exit 2 ;;
  esac
done
if [ -n "$version" ] && [[ ! "$version" =~ ^[0-9a-f]{64}$ ]]; then
  printf '%s\n' 'Invalid selected event version' >&2; exit 2
fi
if [ -n "$snapshot" ] && { [ -L "$snapshot" ] || [ ! -f "$snapshot" ] || [ ! -r "$snapshot" ]; }; then
  printf '%s\n' 'Historical snapshot must be an existing readable regular non-symlink file' >&2; exit 1
fi
# docker ps may shorten its Image display. Select by the complete Config.Image
# from inspect instead, and recheck the running state without exposing Env data.
running_ids=$(docker ps --quiet --no-trunc)
helper_id=''
helper_count=0
image_pattern='^true ghcr[.]io/vbeinlich/eospvprognosehelfer(:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?(@sha256:[0-9a-f]{64})?$'
while IFS= read -r container_id; do
  [ -n "$container_id" ] || continue
  if [[ ! "$container_id" =~ ^[0-9a-f]{12,64}$ ]]; then
    printf '%s\n' 'STOP: unexpected Docker container ID; no export performed.' >&2
    exit 1
  fi
  identity=$(docker inspect --format '{{.State.Running}} {{.Config.Image}}' "$container_id")
  if [[ "$identity" =~ $image_pattern ]]; then
    helper_count=$((helper_count + 1))
    helper_id=$container_id
  fi
done <<< "$running_ids"
if [ "$helper_count" -ne 1 ]; then
  printf '%s\n' 'STOP: could not identify exactly one running helper. Do not start/stop a container.' >&2
  exit 1
fi

# Refuse unexpected/missing mount destinations; never guess alternative paths.
mount_destinations=$(docker inspect --format '{{range .Mounts}}{{println .Destination}}{{end}}' "$helper_id")
printf '%s\n' "$mount_destinations" | awk '$0=="/output" {found=1} END {exit !found}'
printf '%s\n' "$mount_destinations" | awk '$0=="/app/config.toml" {found=1} END {exit !found}'

historical_engine=$(cat <<'PY_ENGINE'
"""Read-only event-bound Doctor evidence, runnable in the existing helper Python.

No network, extraction, timestamp repair, configuration update or optimization.
The wrapper embeds these exact bytes. Python 3.11 standard library only: no
installed helper, EOS, astral, site-packages or development source is required.
"""

import argparse
import bisect
import fcntl
import hashlib
import io
import json
import math
import re
import sys
import tomllib
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_FILE = 8_000_000
MAX_ZIP = 60_000_000
VERSION = re.compile(r"[0-9a-f]{64}")
PRICE_KEY = "elecprice_marketprice_wh"


class ForecastError(ValueError):
    """Sanitized evidence error; no runtime project exception dependency."""


def timestamp(value):
    if not isinstance(value, str):
        raise ForecastError("Historical timestamp must be an ISO-8601 string")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(UTC)
    except ValueError:
        raise ForecastError("Historical timestamp requires a valid explicit UTC offset") from None


def number(value):
    if isinstance(value, bool):
        raise ForecastError("Boolean is not a measurement")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ForecastError("Missing or nonnumeric measurement") from None
    if not math.isfinite(result):
        raise ForecastError("Nonfinite measurement")
    return result


def day_ahead_version(frame, now, timezone):
    # Preserve the native delivery-day hash byte-for-byte, including DST days.
    zone = ZoneInfo(timezone)
    delivery = now.astimezone(zone).date() + timedelta(days=1)
    left = datetime.combine(delivery, datetime.min.time(), zone).astimezone(UTC)
    right = datetime.combine(delivery + timedelta(days=1), datetime.min.time(), zone).astimezone(UTC)
    count = int((right - left).total_seconds() / 900)
    rows = []
    for i in range(count):
        key = (left + timedelta(minutes=15*i)).isoformat()
        if key not in frame["data"]:
            raise ForecastError("Historical next delivery day is incomplete")
        rows.append([key, frame["data"][key][PRICE_KEY]])
    encoded = json.dumps([delivery.isoformat(), rows], separators=(",", ":")).encode()
    return {"version": hashlib.sha256(encoded).hexdigest(), "delivery_day": str(delivery),
            "delivery_intervals": count}


def raw_series(response):
    data = response.get("data")
    if not isinstance(data, dict) or not data:
        raise ForecastError("Historical raw series is empty")
    result = {}
    for key, value in data.items():
        dt = timestamp(key)
        if dt in result:
            raise ForecastError("Duplicate historical raw-series timestamp")
        result[dt] = None if value is None else number(value)
    return result


def interval_averages(values, start, slots, seconds):
    """Bounded interval integration, identical to the inspected input contract."""
    ordered = sorted((key.timestamp(), value) for key, value in values.items())
    if not ordered:
        return [None] * slots
    stamps, samples = zip(*ordered)
    cadence = min([3600] + [b - a for a, b in zip(stamps, stamps[1:])])
    result = []
    for i in range(slots):
        left = start.timestamp() + i * seconds
        right = left + seconds
        position = max(0, bisect.bisect_right(stamps, left) - 1)
        covered, weighted = 0, 0
        while position < len(stamps) and stamps[position] < right:
            end = min(stamps[position] + cadence,
                      stamps[position + 1] if position + 1 < len(stamps) else math.inf)
            overlap = max(0, min(right, end) - max(left, stamps[position]))
            if overlap and samples[position] is not None:
                covered += overlap
                weighted += overlap / seconds * samples[position]
            position += 1
        result.append(weighted if abs(covered - seconds) < 1e-6 else None)
    return result


def event_acceptance(config, values, version, reference):
    """Frozen Doctor checks for one original success, without importing the app."""
    report, state, prices = (values[name] for name in ("sync-report.json", "sync-state.json", "prices.json"))
    claim, event = state["events"][version], report["event"]
    soc, control = report.get("soc", {}), report.get("prices", {}).get("control_coverage", {})
    proof = soc.get("freshness_evidence", {})
    expected = day_ahead_version(prices, timestamp(claim["claimed_at_utc"]), config["timezone"])
    start, claimed = timestamp(claim["start_utc"]), timestamp(claim["claimed_at_utc"])
    checks = {
        "sync_recent": 0 <= (reference - timestamp(report["checked_at_utc"])).total_seconds() <= 450,
        "write_mode": report.get("mode") == "write",
        "sync_no_errors": report.get("errors") == {},
        "imports_verified": all(report.get(key, {}).get("import_verified") is True
                                for key in ("pv", "soc", "prices")),
        "pv_state_verified": state.get("pv_import_verified") is True,
        "price_control_complete": control.get("control_complete") is True
                                  and number(control.get("required_control_hours")) >= 24,
        "soc_usable": soc.get("usable") is True,
        "soc_fresh": 0 <= (reference - timestamp(soc.get("source_timestamp", ""))).total_seconds()
                         <= min(300, config["soc"]["max_age_seconds"]),
        "soc_proof": soc.get("source") == "evcc" and soc.get("freshness_verified") is True
                     and soc.get("timestamp_kind") == "successful_uncached_device_read_lower_bound"
                     and proof.get("contract") == "evcc-0.318.1/e3dc-rscp/uncached-getters",
        "soc_proof_values_match": (
            0 <= number(soc.get("percent")) <= 100
            and number(soc.get("factor")) == number(soc.get("percent")) / 100
            and number(proof.get("live_soc_percent")) == number(soc.get("percent"))
            and abs(number(proof.get("live_power_w"))) <= config["soc"]["max_abs_power_w"]
            and timestamp(soc.get("source_timestamp", "")) == timestamp(proof.get("read_started_at_utc", ""))
            and 0 <= (timestamp(proof.get("read_completed_at_utc", ""))
                      - timestamp(proof.get("read_started_at_utc", ""))).total_seconds() <= 15),
        "no_uncertain_claims": all(isinstance(item, dict) and item.get("status") == "succeeded"
                                   for item in state["events"].values()),
        "delivery_version_matches": all(claim.get(key) == event.get(key) == value
                                        for key, value in expected.items()),
        "plan_matches_claim": all(claim.get(key) == event.get(key) for key in (
            "start_utc", "control_hours", "interval_seconds", "effective_tail_hours")),
        "control_24h": number(claim["control_hours"]) == 24 and claim["interval_seconds"] == 3600,
        "claim_timing": 0 <= (claimed - start).total_seconds() < 3600 and claimed <= reference,
    }
    if claim.get("status") != "succeeded" or event.get("status") != "succeeded":
        raise ForecastError("Selected historical dispatch is not confirmed succeeded")
    solution = values["solution-" + version + ".json"]
    if (solution.get("interval_seconds") != claim["interval_seconds"]
            or timestamp(solution.get("start_solution_datetime", "")) != start):
        raise ForecastError("Historical solution start or interval differs from claim")
    count = int(claim["control_hours"] * 3600 / claim["interval_seconds"])
    for key in ("ac_charge", "dc_charge", "discharge_allowed"):
        controls = solution.get(key)
        if not isinstance(controls, list) or len(controls) < count:
            raise ForecastError("Incomplete historical solution controls")
        for value in controls:
            if not 0 <= number(value) <= 1 or (key == "discharge_allowed" and value not in (0, 1)):
                raise ForecastError("Invalid historical solution control")
    costs = number(solution.get("result", {}).get("total_costs"))
    checks["solution_content_valid"] = True
    if not all(checks.values()):
        raise ForecastError("Historical Doctor blocked: " + ", ".join(key for key, value in checks.items() if not value))
    return {"schema_version": 1, "checked_at_utc": reference.isoformat(), "read_only": True,
            "accepted": True, "status": "accepted", "checks": checks, "event_status": event["status"],
            "plan": {**{key: claim[key] for key in ("delivery_day", "start_utc", "claimed_at_utc",
                     "control_hours", "interval_seconds", "effective_tail_hours")},
                     "version": version, "total_costs": costs}}


def names(version):
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ForecastError("Invalid selected event version")
    return {"sync-report.json", "sync-state.json", "prices.json", "soc.json",
            "forecast.json", "report.json", "solution-" + version + ".json"}


def privacy(value):
    forbidden = {"token", "accesstoken", "refreshtoken", "password", "passwd", "secret",
                 "apikey", "bearertoken", "authorization", "cookie", "clientsecret", "privatekey",
                 "config", "configuration", "tokenfile", "bearertokenfile", "headers"}
    credential = re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
                            r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|"
                            r"Bearer\s+[A-Za-z0-9._-]{12,}")
    if isinstance(value, dict):
        for key, item in value.items():
            if re.sub("[^a-z]", "", key.lower()) in forbidden:
                raise ForecastError("Private export blocked by privacy guard")
            privacy(item)
    elif isinstance(value, list):
        for item in value:
            privacy(item)
    elif isinstance(value, str) and credential.search(value):
        raise ForecastError("Private export blocked by privacy guard")


def decode(raw):
    if len(raw) > MAX_FILE:
        raise ForecastError("Oversized historical artifact")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ForecastError("Historical artifact must be an object")
    privacy(value)
    return value


def read(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ForecastError("Historical input evidence incomplete: missing or unsafe " + name)
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE + 1)
    decode(raw)
    return raw


@contextmanager
def locked(root):
    lock = root / "sync.lock"
    if lock.is_symlink() or not lock.is_file():
        raise ForecastError("Existing sync lock unavailable")
    with lock.open("rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ForecastError("Sync in progress; retry later without stopping it") from None
        yield


def limits(settings):
    soc = settings.get("soc", {})
    age, power = soc.get("max_age_seconds", 300), soc.get("max_abs_power_w", 20000)
    if (isinstance(age, bool) or not isinstance(age, (int, float)) or not 0 < age <= 300
            or isinstance(power, bool) or not isinstance(power, (int, float)) or not 0 < power <= 100000):
        raise ForecastError("Invalid historical validation constraints")
    return {"max_age_seconds": age, "max_abs_power_w": power}


def validate(manifest, files, *, now=None, settings=None):
    """Evaluate unchanged saved inputs at the persisted dispatch claim time."""
    now = now or datetime.now(UTC)
    if manifest.get("schema_version") != 2:
        raise ForecastError("Historical input evidence incomplete: legacy snapshot lacks saved SoC/PV inputs")
    version = manifest.get("event_version")
    expected = names(version)
    if set(files) != expected or set(manifest["files"]) != expected:
        raise ForecastError("Historical input evidence incomplete: expected seven event-bound artifacts")
    if manifest.get("configured_constraints_read") is not True:
        raise ForecastError("Historical configured validation limits not evidenced")
    privacy(manifest)
    captured = timestamp(manifest["captured_at_utc"])
    if captured > now:
        raise ForecastError("Future historical capture time")
    config = {"timezone": manifest["timezone"], "soc": limits({"soc": manifest["validation_constraints"]})}
    if settings is not None:
        if settings.get("timezone", "Europe/Berlin") != config["timezone"]:
            raise ForecastError("Historical timezone differs from operator configuration")
        active = limits(settings)
        config["soc"] = {key: min(value, active[key]) for key, value in config["soc"].items()}
    values = {}
    for name, raw in files.items():
        if hashlib.sha256(raw).hexdigest() != manifest["files"][name]:
            raise ForecastError("Historical artifact SHA256 mismatch: " + name)
        values[name] = decode(raw)
    report, state = values["sync-report.json"], values["sync-state.json"]
    claim = state.get("events", {}).get(version)
    if not isinstance(claim, dict) or claim.get("status") != "succeeded":
        raise ForecastError("Selected historical claim is not succeeded")
    if report.get("event", {}).get("version") != version:
        raise ForecastError("Historical report/event version mismatch; current inputs cannot replace history")
    claimed = timestamp(claim["claimed_at_utc"])
    if not timestamp(report["checked_at_utc"]) <= claimed <= captured:
        raise ForecastError("Historical report, claim and capture chronology inconsistent")
    # soc.json is saved before import_verified is added to the in-memory report.
    reported_soc = {key: value for key, value in report.get("soc", {}).items()
                    if key != "import_verified"}
    saved_soc = {key: value for key, value in values["soc.json"].items() if key != "import_verified"}
    if (saved_soc != reported_soc or ("import_verified" in values["soc.json"]
            and values["soc.json"]["import_verified"] != report["soc"].get("import_verified"))):
        raise ForecastError("Historical SoC artifact differs from selected event report")
    proof = saved_soc.get("freshness_evidence", {})
    if timestamp(proof.get("read_completed_at_utc", "")) > claimed:
        raise ForecastError("Historical SoC read completed after selected dispatch")
    pv = values["report.json"]
    if pv != report.get("pv"):
        raise ForecastError("Historical PV report differs from selected event report")
    if not timestamp(pv["checked_at_utc"]) <= claimed:
        raise ForecastError("Historical forecast was validated after selected dispatch")
    if pv.get("source_fetched_at_utc") and not 0 <= (
        claimed - timestamp(pv["source_fetched_at_utc"])
    ).total_seconds() < number(pv["source_max_age_seconds"]):
        raise ForecastError("Historical PV cache was expired at selected dispatch")
    forecast = values["forecast.json"].get("data", {})
    if not isinstance(forecast, dict) or not forecast or len(forecast) != pv["count"]:
        raise ForecastError("Historical PV input count mismatch")
    series = {}
    for key, row in forecast.items():
        dt, value = timestamp(key), number(row["pvforecast_ac_power"])
        if dt in series or value < 0 or dt.timestamp() % 900:
            raise ForecastError("Invalid historical PV interval")
        series[dt] = value
    stamps = sorted(series)
    if (stamps[0] != timestamp(pv["start_utc"])
            or stamps[-1] + timedelta(minutes=15) != timestamp(pv["end_exclusive_utc"])
            or any(b - a != timedelta(minutes=15) for a, b in zip(stamps, stamps[1:]))):
        raise ForecastError("Historical PV interval bounds or continuity mismatch")
    seconds = claim["interval_seconds"]
    hours = number(claim["control_hours"]) + number(claim["effective_tail_hours"])
    if seconds != 3600 or hours < 24 or hours > 168 or hours * 3600 % seconds:
        raise ForecastError("Unsupported historical plan horizon")
    slots, start = int(hours * 3600 / seconds), timestamp(claim["start_utc"])
    prices = values["prices.json"]
    if len(prices.get("data", {})) != report.get("prices", {}).get("count"):
        raise ForecastError("Historical price snapshot count mismatch")
    price_series = raw_series({"data": {key: row[PRICE_KEY] for key, row in prices["data"].items()}})
    price_stamps = sorted(price_series)
    if (report["prices"].get("unit") != "EUR/Wh"
            or any(dt.timestamp() % 900 for dt in price_stamps)
            or any(b - a != timedelta(minutes=15) for a, b in zip(price_stamps, price_stamps[1:]))):
        raise ForecastError("Historical prices must be continuous 15-minute EUR/Wh intervals")
    if any(value is None for value in interval_averages(series, start, slots, seconds)):
        raise ForecastError("Historical PV input does not cover selected plan")
    if any(value is None for value in interval_averages(price_series, start, slots, seconds)):
        raise ForecastError("Historical price input does not cover selected plan")
    evidence = event_acceptance(config, values, version, claimed)
    evidence.update(evidence_mode="historical_snapshot", current_freshness_verified=False,
                    historical_reference_kind="persisted_claim",
                    evaluated_at_utc=now.isoformat(), captured_at_utc=captured.isoformat(),
                    historical_reference_utc=claimed.isoformat(), event_version=version,
                    provenance="Operator must confirm unchanged historical capture origin; hashes are not authentication")
    evidence["checks"].update(historical_soc_matches=True, historical_pv_matches=True,
                              historical_price_coverage=True, historical_inputs_complete=True)
    evidence["artifact_sha256"] = dict(manifest["files"])
    return evidence


def unpack(raw):
    if len(raw) > MAX_ZIP:
        raise ForecastError("Oversized historical snapshot")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if (len(infos) != 8 or len({i.filename for i in infos}) != 8
                or any(i.file_size > MAX_FILE for i in infos)):
            raise ForecastError("Historical input evidence incomplete: expected snapshot manifest and seven artifacts")
        manifest = decode(archive.read("snapshot.json"))
        expected = names(manifest.get("event_version"))
        if {i.filename for i in infos} != expected | {"snapshot.json"}:
            raise ForecastError("Historical archive names do not match selected event")
        return manifest, {name: archive.read(name) for name in expected}


def pack(manifest, files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("snapshot.json", json.dumps(manifest, indent=2))
        for name, raw in files.items():
            archive.writestr(name, raw)
    return stream.getvalue()


def manifest_digest(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return hashlib.sha256(archive.read("snapshot.json")).hexdigest()


def prepare(directory, settings, *, historical=None, event_version=None, now=None):
    """Select one original evidence set, under a shared lock on live state/solution."""
    root, now = Path(directory), now or datetime.now(UTC)
    with locked(root):
        state = decode(read(root, "sync-state.json"))
        if historical is not None:
            manifest, files = unpack(historical)
            version = manifest["event_version"]
            if event_version is not None and event_version != version:
                raise ForecastError("Selected version differs from historical archive version")
        else:
            report = decode(read(root, "sync-report.json"))
            version = event_version or report.get("event", {}).get("version")
            if (not version or report.get("event", {}).get("version") != version
                    or report.get("event", {}).get("status") != "succeeded"):
                count = sum(isinstance(c, dict) and c.get("status") == "succeeded"
                            for c in state.get("events", {}).values())
                raise ForecastError("Historical input evidence incomplete: latest report has no matching succeeded event; "
                    + ("waiting-publication; " if report.get("event", {}).get("status") == "waiting-publication" else "")
                    + str(count) + " succeeded claim(s) do not prove saved prices/SoC/PV. "
                    "Provide an existing complete --historical-snapshot; never combine current inputs with old solutions")
            files = {name: read(root, name) for name in names(version)}
            manifest = {"schema_version": 2, "event_version": version,
                        "captured_at_utc": now.isoformat(), "timezone": settings.get("timezone", "Europe/Berlin"),
                        "configured_constraints_read": True, "validation_constraints": limits(settings),
                        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
        saved = decode(files["sync-state.json"]).get("events", {}).get(version)
        if saved != state.get("events", {}).get(version) or not isinstance(saved, dict):
            raise ForecastError("Historical claim differs from persisted selected claim")
        solution = "solution-" + version + ".json"
        if read(root, solution) != files[solution]:
            raise ForecastError("Historical solution bytes differ from persisted selected solution")
        evidence = validate(manifest, files, now=now, settings=settings)
        evidence.update(shared_lock_verified=True, persisted_event_verified=True)
        # An existing archive is never repacked or assigned a new capture time.
        raw = historical if historical is not None else pack(manifest, files)
        evidence["capture_manifest_sha256"] = manifest_digest(raw)
        return evidence, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Existing live output; only read under shared lock")
    parser.add_argument("--config", help="Read validation limits, never export configuration")
    parser.add_argument("--snapshot", help="Existing historical ZIP, or - for stdin")
    parser.add_argument("--event-version")
    parser.add_argument("--check-only", action="store_true", help="Sanitized preflight status only")
    parser.add_argument("--emit", action="store_true", help="Emit verified original ZIP bytes, not JSON")
    args = parser.parse_args()
    try:
        settings = tomllib.loads(Path(args.config).read_text()) if args.config else {}
        raw = None
        if args.snapshot:
            if args.snapshot == "-":
                raw = sys.stdin.buffer.read(MAX_ZIP + 1)
            else:
                path = Path(args.snapshot)
                if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ZIP:
                    raise ForecastError("Missing, unsafe or oversized historical snapshot")
                with path.open("rb") as handle:
                    raw = handle.read(MAX_ZIP + 1)
        if args.source:
            if not args.config:
                raise ForecastError("Source validation requires explicit validation configuration")
            evidence, raw = prepare(args.source, settings, historical=raw, event_version=args.event_version)
        elif raw is not None:
            manifest, files = unpack(raw)
            if args.event_version and args.event_version != manifest["event_version"]:
                raise ForecastError("Selected version differs from historical archive version")
            evidence = validate(manifest, files)
            evidence["capture_manifest_sha256"] = manifest_digest(raw)
        else:
            raise ForecastError("Provide existing source artifacts or a historical snapshot")
        if args.emit:
            if args.check_only:
                raise ForecastError("Choose preflight or export, not both")
            sys.stdout.buffer.write(raw)
        elif args.check_only:
            print(json.dumps({"preflight": "passed", "read_only": True,
                "shared_lock_verified": evidence.get("shared_lock_verified", False),
                "artifact_count": 7, "export_created": False, "doctor_acceptance": False}))
        else:
            print(json.dumps(evidence))
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ForecastError) else "Invalid historical artifacts; no files changed"
        print(json.dumps({"accepted": False, "read_only": True, "status": "blocked", "reason": reason}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY_ENGINE
)
engine_sha256=d4d713cd53c3a94621032ea7aeb2c76b5787b96e53ec8658544ab248c896a564
# Pin the reviewed embedded engine; no download or container installation.
actual_engine_sha256=$(printf '%s' "$historical_engine" | sha256sum)
[ "${actual_engine_sha256%% *}" = "$engine_sha256" ] || { printf '%s\n' 'Embedded Doctor SHA256 mismatch' >&2; exit 1; }
arguments=(--source /output --config /app/config.toml)
if [ -n "$version" ]; then arguments+=(--event-version "$version"); fi
if [ -n "$snapshot" ]; then arguments+=(--snapshot -); fi
run_doctor() {
  if [ -n "$snapshot" ]; then
    docker exec -i "$helper_id" python -I -S -B -c "$historical_engine" "${arguments[@]}" "$@" < "$snapshot"
  else
    docker exec -i "$helper_id" python -I -S -B -c "$historical_engine" "${arguments[@]}" "$@" < /dev/null
  fi
}
# A successful check is not a perpetual approval; export takes its own shared lock.
if [ "$mode" = '--check-only' ]; then
  run_doctor --check-only
  exit 0
fi
run_doctor --check-only
accept_dir=$(mktemp -d /tmp/eos-v010-doctor.XXXXXXXX)
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$accept_dir/operator-observed-at-utc.txt"
printf '%s\n' "$engine_sha256" > "$accept_dir/historical-engine-sha256.txt"
printf '%s' "$historical_engine" > "$accept_dir/historical-doctor.py"
docker inspect --format '{"container_id":{{json .Id}},"name":{{json .Name}},"configured_image":{{json .Config.Image}},"image_id":{{json .Image}}}' \
  "$helper_id" > "$accept_dir/runtime.json"
image_id=$(docker inspect --format '{{.Image}}' "$helper_id")
docker image inspect --format '{"source":{{json (index .Config.Labels "org.opencontainers.image.source")}},"revision":{{json (index .Config.Labels "org.opencontainers.image.revision")}},"version":{{json (index .Config.Labels "org.opencontainers.image.version")}}}' \
  "$image_id" > "$accept_dir/image-origin.json"
# Validation/privacy checks finish in memory before any ZIP byte is emitted.
# Existing historical archives keep their exact bytes and original capture time.
run_doctor --emit \
  | docker exec -i "$helper_id" python -I -S -B -c "$historical_engine" --snapshot - --emit \
  > "$accept_dir/doctor-snapshot.zip.partial"
mv -- "$accept_dir/doctor-snapshot.zip.partial" "$accept_dir/doctor-snapshot.zip"
sha256sum "$accept_dir/doctor-snapshot.zip" "$accept_dir/historical-doctor.py" \
  "$accept_dir/historical-engine-sha256.txt" "$accept_dir/runtime.json" \
  "$accept_dir/image-origin.json" "$accept_dir/operator-observed-at-utc.txt" \
  > "$accept_dir/SHA256SUMS.txt"
printf 'Export successful; private directory: %s\n' "$accept_dir"
printf '%s\n' 'Keep ALL files private. Transfer securely, never to GitHub.'
printf '%s\n' 'This is an export, not Doctor acceptance. Validate offline; never backdate timestamps.'

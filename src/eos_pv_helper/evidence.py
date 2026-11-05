"""Opt-in, private, no-overwrite event archives. Caller holds sync.lock EX.

No HTTP, optimization, state repair, old-input reconstruction or retention deletion.
Only complete validated ready files can be recovered after interruption.
"""

import fcntl
import hashlib
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from . import economics
from . import historical as doctor
from .event_context import canonical_sha, observed_options, solution_inputs

DIRECTORY = "genetic-evidence"
INPUTS = {"prices.json", "soc.json", "forecast.json", "report.json"}
REPLAY_ADMISSION = "eos-pv-helper/replay-ready-archive-v1"
SERIES = {"pvforecast_ac_power": "pv_forecast_wh", "loadforecast_power_w": "total_load",
          "elecprice_marketprice_wh": "electricity_price_per_wh",
          "feed_in_tariff_wh": "feed_in_tariff_per_wh"}


class EvidenceError(ValueError):
    """Safe diagnostic; never include OS paths, config or raw measurement values."""


def enabled(config):
    return config.get("evidence", {}).get("enabled") is True


def capture_inputs(output, report, frame, series, plan, clock, settings=None):
    """Freeze bytes read for THIS dispatch, not files observed after the POST."""
    files = {name: doctor.read(Path(output), name) for name in INPUTS}
    values = {name: doctor.decode(raw) for name, raw in files.items()}
    if values["prices.json"] != frame:
        raise EvidenceError("dispatch_prices_differ")
    soc = {k: v for k, v in report["soc"].items() if k != "import_verified"}
    saved_soc = {k: v for k, v in values["soc.json"].items() if k != "import_verified"}
    if saved_soc != soc:
        raise EvidenceError("dispatch_soc_differ")
    if values["report.json"] != report["pv"]:
        raise EvidenceError("dispatch_pv_report_differ")
    forecast = values["forecast.json"].get("data", {})
    start = doctor.timestamp(plan["start_utc"])
    end = start + timedelta(hours=plan["control_hours"] + plan["effective_tail_hours"])
    position = start
    while position < end:
        row = forecast.get(position.isoformat(), {})
        if row.get("pvforecast_ac_power") != series["pvforecast_ac_power"].get(position):
            raise EvidenceError("dispatch_pv_series_differ")
        if row.get("pvforecast_ac_power") is None:
            raise EvidenceError("dispatch_pv_interval_missing")
        position += timedelta(minutes=15)
    slots = int((end-start).total_seconds() / plan["interval_seconds"])
    frozen = {target: doctor.interval_averages(series[source], start, slots, plan["interval_seconds"])
              for source, target in SERIES.items()}
    if any(value is None for values in frozen.values() for value in values):
        raise EvidenceError("dispatch_solver_series_incomplete")
    return {"files": files, "captured_at_utc": clock().isoformat(),
            "dispatch_series_binding": {"contract": REPLAY_ADMISSION,
                "start_utc": plan["start_utc"], "interval_seconds": plan["interval_seconds"],
                "series": frozen, "series_sha256": canonical_sha(frozen)},
            "observed_options": observed_options(settings or {})}


def _replay_admission(manifest, files, evidence):
    """Same v2 admission as PR #27, plus a structural projection; no model execution."""
    if not (evidence["accepted"] and evidence["input_binding_complete"]
            and evidence["validation_scope"] == "request_solver_inputs"
            and all(evidence["checks"].values())
            and manifest.get("producer", {}).get("contract") ==
            "eos-pv-helper/automatic-evidence-v1"
            and evidence["runtime_context"]["status"] ==
            "consistent_observation_and_returned_inputs"):
        raise EvidenceError("archive_replay_binding_not_proven")
    solution = doctor.decode(files["solution-" + manifest["event_version"] + ".json"])
    try:
        economics.project(solution)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise EvidenceError("archive_saved_model_not_replay_compatible") from None
    binding = manifest["producer"].get("dispatch_series_binding")
    if binding is not None:
        claim = doctor.decode(files["sync-state.json"])["events"][manifest["event_version"]]
        slots = int((claim["control_hours"]+claim["effective_tail_hours"])*3600 / claim["interval_seconds"])
        if (binding.get("contract") != REPLAY_ADMISSION
                or binding.get("start_utc") != claim["start_utc"]
                or binding.get("interval_seconds") != claim["interval_seconds"]
                or set(binding.get("series", {})) != set(SERIES.values())
                or canonical_sha(binding["series"]) != binding.get("series_sha256")):
            raise EvidenceError("archive_dispatch_series_binding_invalid")
        for key, values in binding["series"].items():
            actual = solution["parameters"]["ems"][key]
            if (not isinstance(values, list) or len(values) != slots or len(actual) < slots
                    or any(not doctor.close_values(a, b, energy=key in ("pv_forecast_wh", "total_load"))
                           for a, b in zip(actual, values))):
                raise EvidenceError("archive_dispatch_solver_series_differ")


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _directory(path):
    if path.is_symlink():
        raise EvidenceError("unsafe_archive_directory")
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    else:
        _sync_directory(path.parent)
    if not path.is_dir() or path.stat().st_mode & 0o077:
        raise EvidenceError("archive_directory_must_be_private")
    return path


@contextmanager
def _writer(output):
    root = _directory(Path(output) / DIRECTORY)
    pending = _directory(root / ".pending")
    path = root / "archive.lock"
    if path.is_symlink():
        raise EvidenceError("unsafe_archive_lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield root, pending


def _raw(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > doctor.MAX_ZIP:
        raise EvidenceError("archive_missing_unsafe_or_oversized")
    with path.open("rb") as handle:
        return handle.read(doctor.MAX_ZIP + 1)


def _verify(raw, config, version, claim, solution_sha, clock):
    manifest, files = doctor.unpack(raw)
    if manifest["event_version"] != version:
        raise EvidenceError("archive_event_version_differ")
    saved = doctor.decode(files["sync-state.json"]).get("events", {}).get(version)
    if saved != claim or claim.get("status") != "succeeded":
        raise EvidenceError("archive_persisted_success_differ")
    if manifest["files"]["solution-" + version + ".json"] != solution_sha:
        raise EvidenceError("archive_solution_differ")
    evidence = doctor.validate(manifest, files, now=clock(), settings=config)
    if not evidence["input_binding_complete"]:
        raise EvidenceError("archive_legacy_limited_request_binding_missing")
    _replay_admission(manifest, files, evidence)
    return manifest


def inspect_archive(output, config, version, claim, solution_sha, clock):
    doctor.names(version)
    root = Path(output) / DIRECTORY
    if root.is_symlink():
        raise EvidenceError("unsafe_archive_directory")
    raw = _raw(root / (version + ".zip"))
    manifest = _verify(raw, config, version, claim, solution_sha, clock)
    return {"status": "archived", "archive": DIRECTORY + "/" + version + ".zip",
            "sha256": hashlib.sha256(raw).hexdigest(), "captured_at_utc": manifest["captured_at_utc"],
            "validation_contract": doctor.VALIDATION_CONTRACT, "validation_scope": "request_solver_inputs",
            "input_binding_complete": True,
            "replay_admission": {"contract": REPLAY_ADMISSION, "status": "ready_for_native_replay",
                                 "native_result_verified": False}}


def _publish(root, pending, raw, version, verify):
    """Ready/final hard links provide atomic exclusive publication, never replace."""
    target, ready = root / (version + ".zip"), pending / (version + ".ready")
    manifest = verify(raw)
    for existing in (target, ready):
        if existing.exists() or existing.is_symlink():
            if canonical_sha(verify(_raw(existing))) != canonical_sha(manifest):
                raise EvidenceError("archive_conflict_preserved")
    if not target.exists():
        if not ready.exists():
            if shutil.disk_usage(root).free < len(raw) + 1024*1024:
                raise EvidenceError("archive_insufficient_disk_space")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=pending, prefix=".writing-" + version + "-",
                                                 delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(raw)
                    handle.flush()
                    os.fchmod(handle.fileno(), 0o400)
                    os.fsync(handle.fileno())
                # A ready file is complete and independently validated before publication.
                verify(_raw(temporary))
                os.link(temporary, ready)
                _sync_directory(pending)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)  # Only this invocation's own temporary file.
        try:
            os.link(ready, target)
        except FileExistsError:
            if canonical_sha(verify(_raw(target))) != canonical_sha(manifest):
                raise EvidenceError("archive_conflict_preserved") from None
        _sync_directory(root)
    # Final archive is never deleted. Remove only our validated staging link.
    if ready.exists():
        ready.unlink()
        _sync_directory(pending)


def archive_success(output, config, captured, state, report, clock):
    """Called only AFTER original succeeded state, report and solution are durable."""
    version = report["event"]["version"]
    doctor.names(version)
    files = dict(captured["files"])
    for name in ("sync-state.json", "sync-report.json", "solution-" + version + ".json"):
        files[name] = doctor.read(Path(output), name)
    if doctor.decode(files["sync-state.json"]) != state or doctor.decode(files["sync-report.json"]) != report:
        raise EvidenceError("original_success_cycle_differ")
    now = clock()
    manifest = {"schema_version": 2, "event_version": version, "captured_at_utc": now.isoformat(),
        "timezone": config.get("timezone", "Europe/Berlin"), "configured_constraints_read": True,
        "validation_constraints": doctor.limits(config),
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
        "producer": {"contract": "eos-pv-helper/automatic-evidence-v1",
                     "input_captured_at_utc": captured["captured_at_utc"],
                     "claimed_at_utc": state["events"][version]["claimed_at_utc"],
                     "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                     "doctor_engine_sha256": hashlib.sha256(Path(doctor.__file__).read_bytes().rstrip(b"\n")).hexdigest()}}
    context = captured["observed_options"]
    manifest["producer"].update(observed_options=context, observed_options_sha256=canonical_sha(context),
        dispatched_request_sha256=captured.get("dispatched_request_sha256"),
        dispatch_series_binding=captured["dispatch_series_binding"],
        solution_inputs=solution_inputs(doctor.decode(files["solution-" + version + ".json"])))
    if not doctor.timestamp(captured["captured_at_utc"]) <= doctor.timestamp(
        state["events"][version]["claimed_at_utc"]) <= now:
        raise EvidenceError("input_capture_dispatch_chronology_differ")
    raw = doctor.pack(manifest, files)
    claim = state["events"][version]
    solution_sha = manifest["files"]["solution-" + version + ".json"]
    def verify(value):
        return _verify(value, config, version, claim, solution_sha, clock)
    with _writer(output) as (root, pending):
        _publish(root, pending, raw, version, verify)
    return inspect_archive(output, config, version, claim, solution_sha, clock)


def recover_ready(output, config, state, clock):
    """Recover ORIGINAL complete bytes only. Never manufacture a missing old report."""
    pending = Path(output) / DIRECTORY / ".pending"
    if not pending.exists():
        return []
    if pending.is_symlink() or pending.parent.is_symlink():
        raise EvidenceError("unsafe_archive_directory")
    recovered = []
    with _writer(output) as (root, pending):
        for count, ready in enumerate(pending.glob("*.ready")):
            if count >= 1024:
                raise EvidenceError("too_many_pending_archives_operator_review_required")
            version = ready.stem
            doctor.names(version)
            claim = state.get("events", {}).get(version, {})
            solution_sha = hashlib.sha256(doctor.read(Path(output), "solution-" + version + ".json")).hexdigest()
            raw = _raw(ready)
            def verify(value):
                return _verify(value, config, version, claim, solution_sha, clock)
            _publish(root, pending, raw, version, verify)
            recovered.append(version)
    return recovered


def diagnostic(exc):
    if isinstance(exc, EvidenceError):
        return str(exc)
    if isinstance(exc, doctor.ForecastError):
        return "invalid_incomplete_or_private_evidence"
    return "archive_io_or_validation_failed"

"""Synthetic event inputs only; no production export or optimization."""

import ast
import copy
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import test_doctor as legacy

from eos_pv_helper.doctor import snapshot_acceptance
from eos_pv_helper.historical import ForecastError, pack, prepare, unpack, validate

NOW = legacy.NOW


def complete_artifacts(directory):
    root, config, files = legacy.artifacts.__wrapped__(directory)
    start = NOW.replace(hour=0, minute=0)
    forecast = {"data": {(start + timedelta(minutes=15*i)).isoformat():
                           {"pvforecast_ac_power": 1000 if 6 <= i % 96 < 72 else 0}
                          for i in range(288)}}
    pv = {"checked_at_utc": NOW.isoformat(), "count": 288,
          "start_utc": start.isoformat(), "end_exclusive_utc": (start+timedelta(hours=72)).isoformat(),
          "import_verified": True, "source_fetched_at_utc": NOW.isoformat(),
          "source_max_age_seconds": 3600}
    files["sync-report.json"]["pv"] = pv
    files["sync-report.json"]["prices"].update(count=192, unit="EUR/Wh")
    files["report.json"], files["forecast.json"] = copy.deepcopy(pv), forecast
    files["soc.json"] = {k: v for k, v in files["sync-report.json"]["soc"].items() if k != "import_verified"}
    for name, value in files.items():
        (root / name).write_text(json.dumps(value))
    return root, config, files


@pytest.fixture
def artifacts(tmp_path):
    return complete_artifacts(tmp_path)


def snapshot(artifacts):
    root, config, _ = artifacts
    return prepare(root, config, now=NOW)[1]


def write(root, name, value):
    (root / name).write_text(json.dumps(value))


def waiting(artifacts):
    root, _, files = artifacts
    report = copy.deepcopy(files["sync-report.json"])
    report.update(checked_at_utc=(NOW+timedelta(days=2)).isoformat(), event={"status": "waiting-publication"})
    write(root, "sync-report.json", report)
    return report


def second_claim(artifacts):
    root, _, files = artifacts
    state = copy.deepcopy(files["sync-state.json"])
    claim = copy.deepcopy(next(iter(state["events"].values())))
    claim["version"] = "a"*64
    state["events"]["a"*64] = claim
    write(root, "sync-state.json", state)
    solution = next(v for n, v in files.items() if n.startswith("solution-"))
    write(root, "solution-"+"a"*64+".json", solution)


def test_waiting_report_two_successes_and_solutions_are_not_complete_evidence(artifacts):
    root, config, _ = artifacts
    waiting(artifacts)
    second_claim(artifacts)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
    with pytest.raises(ForecastError, match="2 succeeded claim.*do not prove saved prices/SoC/PV"):
        prepare(root, config)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}


def test_old_success_uses_only_original_inputs_despite_waiting_and_new_prices(artifacts, monkeypatch):
    root, config, files = artifacts
    raw = snapshot(artifacts)
    manifest, original = unpack(raw)
    waiting(artifacts)
    second_claim(artifacts)
    # Deliberately incompatible live price, PV and SoC data must never be read.
    for name in ("prices.json", "soc.json", "forecast.json", "report.json"):
        (root / name).write_text('{"not_historical": true}')
    monkeypatch.setattr("eos_pv_helper.app.request_json", lambda *a, **k: pytest.fail("HTTP"))
    evidence, emitted = prepare(root, config, historical=raw, event_version=manifest["event_version"],
                                now=NOW+timedelta(days=2))
    assert emitted == raw
    assert evidence["accepted"] and all(evidence["checks"].values())
    assert evidence["historical_reference_utc"] == files["sync-report.json"]["event"]["claimed_at_utc"]
    assert evidence["current_freshness_verified"] is False
    assert evidence["captured_at_utc"] == NOW.isoformat()
    assert len(evidence["artifact_sha256"]) == 7
    assert original["prices.json"] != (root / "prices.json").read_bytes()


@pytest.mark.parametrize("name", ["prices.json", "soc.json", "forecast.json", "report.json"])
def test_missing_historical_input_cannot_be_replaced_by_current_file(artifacts, name):
    raw = snapshot(artifacts)
    manifest, files = unpack(raw)
    del files[name]
    with pytest.raises(ForecastError, match="incomplete"):
        unpack(pack(manifest, files))


@pytest.mark.parametrize("failure", ["report-version", "claim-version", "prices", "soc", "soc-after-claim",
    "soc-stale", "pv-report", "pv-gap", "pv-bounds", "pv-after-claim", "pv-expired", "price-gap",
    "solution", "hash", "future-capture", "privacy", "weak-age", "uncertain"])
def test_inconsistent_historical_inputs_are_rejected_even_with_rehashed_manifest(artifacts, failure):
    manifest, files = unpack(snapshot(artifacts))
    values = {n: json.loads(raw) for n, raw in files.items()}
    report = values["sync-report.json"]
    version = manifest["event_version"]
    if failure == "report-version":
        report["event"]["version"] = "b"*64
    elif failure == "claim-version":
        values["sync-state.json"]["events"][version]["delivery_day"] = "2026-11-02"
    elif failure == "prices":
        values["prices.json"]["data"]["2026-10-30T01:00:00+00:00"][legacy.PRICE_KEY] = .0009
    elif failure in ("soc", "soc-stale", "soc-after-claim"):
        if failure == "soc":
            values["soc.json"]["percent"] = 54
        else:
            if failure == "soc-stale":
                report["soc"]["source_timestamp"] = (NOW-timedelta(seconds=301)).isoformat()
            else:
                report["soc"]["freshness_evidence"]["read_completed_at_utc"] = (NOW+timedelta(seconds=1)).isoformat()
            values["soc.json"] = {k: v for k, v in report["soc"].items() if k != "import_verified"}
    elif failure == "pv-report":
        values["report.json"]["count"] -= 1
    elif failure == "pv-gap":
        values["forecast.json"]["data"].pop(next(iter(values["forecast.json"]["data"])))
    elif failure == "pv-bounds":
        report["pv"]["end_exclusive_utc"] = NOW.isoformat()
        values["report.json"] = report["pv"]
    elif failure == "pv-after-claim":
        report["pv"]["checked_at_utc"] = (NOW+timedelta(seconds=1)).isoformat()
        values["report.json"] = report["pv"]
    elif failure == "pv-expired":
        report["pv"]["source_fetched_at_utc"] = (NOW-timedelta(hours=2)).isoformat()
        values["report.json"] = report["pv"]
    elif failure == "price-gap":
        values["prices.json"]["data"].pop(next(iter(values["prices.json"]["data"])))
    elif failure == "solution":
        values["solution-"+version+".json"]["interval_seconds"] = 900
    elif failure == "future-capture":
        manifest["captured_at_utc"] = (NOW+timedelta(days=10)).isoformat()
    elif failure == "privacy":
        report["token"] = "synthetic-private-value"
    elif failure == "weak-age":
        manifest["validation_constraints"]["max_age_seconds"] = 301
    elif failure == "uncertain":
        values["sync-state.json"]["events"][version]["status"] = "uncertain"
    files = {n: json.dumps(v).encode() for n, v in values.items()}
    manifest["files"] = {n: hashlib.sha256(raw).hexdigest() for n, raw in files.items()}
    if failure == "hash":
        files["prices.json"] += b" "
    with pytest.raises((ForecastError, ValueError)):
        validate(manifest, files, now=NOW+timedelta(days=1))


@pytest.mark.parametrize("failure", ["wrong-selection", "persisted-claim", "persisted-solution"])
def test_selected_event_must_match_live_persisted_success(artifacts, failure):
    root, config, files = artifacts
    raw = snapshot(artifacts)
    args = {}
    if failure == "wrong-selection":
        args["event_version"] = "a"*64
    elif failure == "persisted-claim":
        state = copy.deepcopy(files["sync-state.json"])
        next(iter(state["events"].values()))["effective_tail_hours"] = 8
        write(root, "sync-state.json", state)
    else:
        name = next(n for n in files if n.startswith("solution-"))
        (root / name).write_bytes((root / name).read_bytes()+b" ")
    with pytest.raises(ForecastError, match="differs|differ"):
        prepare(root, config, historical=raw, now=NOW+timedelta(days=1), **args)


def test_offline_doctor_accepts_complete_snapshot_without_live_files(artifacts):
    raw = snapshot(artifacts)
    path = artifacts[0] / "private.zip"
    path.write_bytes(raw)
    result, status = snapshot_acceptance(path, now=NOW+timedelta(days=3))
    assert status == 0 and result["accepted"]
    assert result["evidence_mode"] == "historical_snapshot"
    assert result["historical_reference_kind"] == "persisted_claim"
    assert result["current_freshness_verified"] is False


def test_zip_extra_names_and_traversal_are_rejected(artifacts):
    raw = snapshot(artifacts)
    stream = io.BytesIO(raw)
    with zipfile.ZipFile(stream, "a") as archive:
        archive.writestr("../secret", b"private")
    with pytest.raises(ForecastError):
        unpack(stream.getvalue())


def test_engine_imports_only_python_standard_library():
    from eos_pv_helper import historical
    tree = ast.parse(Path(historical.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split('.')[0] in sys.stdlib_module_names for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module.split('.')[0] in sys.stdlib_module_names


def test_isolated_cli_without_site_packages_reports_waiting_without_traceback(artifacts, tmp_path):
    from eos_pv_helper import historical
    waiting(artifacts)
    second_claim(artifacts)
    config = tmp_path / "limits.toml"
    config.write_text('timezone="Europe/Berlin"\n')
    result = subprocess.run([sys.executable, "-I", "-S", "-B", historical.__file__, "--source",
        str(artifacts[0]), "--config", str(config), "--check-only"], capture_output=True, text=True)
    assert result.returncode == 1
    evidence = json.loads(result.stderr)
    assert evidence["read_only"] and not evidence["accepted"]
    assert "waiting-publication" in evidence["reason"]
    assert "2 succeeded claim(s)" in evidence["reason"]
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("day,intervals", [("2026-03-28", 92), ("2026-10-24", 100), ("2026-10-29", 96)])
def test_standalone_delivery_hash_matches_native_contract_including_dst(day, intervals):
    from eos_pv_helper.historical import day_ahead_version
    from eos_pv_helper.inputs import day_ahead_version as native_version
    now = datetime.fromisoformat(day).replace(hour=13, tzinfo=UTC)
    origin = now.replace(hour=0)
    frame = {"data": {(origin + timedelta(minutes=15*i)).isoformat():
                      {legacy.PRICE_KEY: .0003} for i in range(288)}}
    result = day_ahead_version(frame, now, "Europe/Berlin")
    assert result == native_version(frame, now, "Europe/Berlin")
    assert result["delivery_intervals"] == intervals


@pytest.mark.parametrize("failure", ["none", "mode", "error", "import", "control", "soc-proof",
    "soc-factor", "soc-power", "uncertain", "report-age", "event-status", "tail", "cost", "controls"])
def test_standalone_checks_preserve_native_doctor_rejection_contract(artifacts, failure):
    from eos_pv_helper.doctor import acceptance
    from eos_pv_helper.historical import event_acceptance
    values = copy.deepcopy(artifacts[2])
    report = values["sync-report.json"]
    version = report["event"]["version"]
    if failure == "mode":
        report["mode"] = "dry-run"
    elif failure == "error":
        report["errors"] = {"event": "synthetic"}
    elif failure == "import":
        report["prices"]["import_verified"] = False
    elif failure == "control":
        report["prices"]["control_coverage"]["control_complete"] = False
    elif failure == "soc-proof":
        report["soc"]["freshness_verified"] = False
    elif failure == "soc-factor":
        report["soc"]["factor"] = .1
    elif failure == "soc-power":
        report["soc"]["freshness_evidence"]["live_power_w"] = 999999
    elif failure == "uncertain":
        values["sync-state.json"]["events"]["a"*64] = {"status": "uncertain"}
    elif failure == "report-age":
        report["checked_at_utc"] = (NOW-timedelta(seconds=451)).isoformat()
    elif failure == "event-status":
        report["event"]["status"] = "uncertain"
    elif failure == "tail":
        report["event"]["effective_tail_hours"] = 8
    elif failure == "cost":
        values["solution-"+version+".json"]["result"]["total_costs"] = float("nan")
    elif failure == "controls":
        values["solution-"+version+".json"]["ac_charge"] = [1.1]*24
    config = {"timezone": "Europe/Berlin", "soc": {"max_age_seconds": 300, "max_abs_power_w": 20000}}
    original, status = acceptance(config, now=NOW, _reader=lambda name: (values[name], "f"*64))
    if status:
        with pytest.raises(ForecastError):
            event_acceptance(config, values, version, NOW)
    else:
        result = event_acceptance(config, values, version, NOW)
        assert result["checks"] == original["checks"]
        assert result["plan"] == original["plan"]

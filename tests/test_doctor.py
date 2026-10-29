import copy
import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from eos_pv_helper.app import main
from eos_pv_helper.doctor import acceptance
from eos_pv_helper.inputs import PRICE_KEY, day_ahead_version

NOW = datetime(2026, 10, 29, 13, 5, tzinfo=UTC)


@pytest.fixture
def artifacts(tmp_path):
    prices = {"data": {(NOW.replace(hour=0, minute=0) + timedelta(minutes=15*i)).isoformat():
                        {PRICE_KEY: .0003} for i in range(192)}}
    version = day_ahead_version(prices, NOW)
    claim = {**version, "start_utc": NOW.replace(minute=0).isoformat(),
             "claimed_at_utc": NOW.isoformat(), "control_hours": 24, "interval_seconds": 3600,
             "effective_tail_hours": 10, "status": "succeeded"}
    report = {"checked_at_utc": NOW.isoformat(), "mode": "write", "errors": {},
        "pv": {"import_verified": True}, "prices": {"import_verified": True,
            "control_coverage": {"control_complete": True, "required_control_hours": 24}},
        "soc": {"import_verified": True, "usable": True, "source": "evcc",
            "freshness_verified": True, "source_timestamp": NOW.isoformat(),
            "percent": 55, "factor": .55,
            "timestamp_kind": "successful_uncached_device_read_lower_bound",
            "freshness_evidence": {"contract": "evcc-0.318.1/e3dc-rscp/uncached-getters",
                "live_soc_percent": 55, "live_power_w": -354,
                "read_started_at_utc": NOW.isoformat(), "read_completed_at_utc": NOW.isoformat()}},
        "event": copy.deepcopy(claim)}
    files = {"sync-state.json": {"pv_import_verified": True, "events": {version["version"]: claim}},
        "sync-report.json": report, "prices.json": prices,
        "solution-" + version["version"] + ".json": {
            "interval_seconds": 3600, "start_solution_datetime": claim["start_utc"],
            "ac_charge": [0.] * 24, "dc_charge": [1.] * 24, "discharge_allowed": [1.] * 24,
            "result": {"total_costs": -1.25}}}
    (tmp_path / "sync.lock").touch()
    return tmp_path, {"output": {"directory": str(tmp_path)}}, files


def inspect(artifacts, now=NOW):
    folder, config, files = artifacts
    for name, value in files.items():
        (folder / name).write_text(json.dumps(value))
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    evidence, status = acceptance(config, now=now)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}
    return evidence, status


def test_real_artifact_contract_accepted_without_http_or_writes(artifacts, monkeypatch):
    monkeypatch.setattr("eos_pv_helper.app.request_json", lambda *a, **kw: pytest.fail("HTTP"))
    evidence, status = inspect(artifacts)
    assert status == 0 and evidence["accepted"] and all(evidence["checks"].values())
    assert evidence["plan"]["total_costs"] == -1.25
    assert len(evidence["artifact_sha256"]) == 4


@pytest.mark.parametrize("failure", ["missing", "truncated", "nan", "wrong-start", "wrong-interval",
    "uncertain", "event-claim-differ", "price-version", "future-price", "soc-stale", "soc-unproven",
    "dry-run", "errors", "missing-import", "price-coverage", "stale-report", "bad-version",
    "proof-soc", "proof-time", "proof-power", "control-out-of-range", "discharge-fraction"])
def test_false_success_is_rejected(artifacts, failure):
    _, _, files = artifacts
    report, state = files["sync-report.json"], files["sync-state.json"]
    name = next(k for k in files if k.startswith("solution-"))
    if failure == "missing":
        del files[name]
    elif failure == "truncated":
        files[name]["ac_charge"] = [0] * 23
    elif failure == "nan":
        files[name]["result"]["total_costs"] = float("nan")
    elif failure == "wrong-start":
        files[name]["start_solution_datetime"] = (NOW - timedelta(hours=2)).isoformat()
    elif failure == "wrong-interval":
        files[name]["interval_seconds"] = 900
    elif failure == "uncertain":
        next(iter(state["events"].values()))["status"] = "uncertain"
    elif failure == "event-claim-differ":
        report["event"]["effective_tail_hours"] = 5
    elif failure == "price-version":
        next(iter(files["prices.json"]["data"].values()))[PRICE_KEY] = .0004
        # Mutate a tomorrow value; today's history is deliberately excluded from the hash.
        files["prices.json"]["data"]["2026-10-30T01:00:00+00:00"][PRICE_KEY] = .0004
    elif failure == "future-price":
        files["prices.json"]["data"].pop("2026-10-30T01:00:00+00:00")
    elif failure == "soc-stale":
        report["soc"]["source_timestamp"] = (NOW - timedelta(seconds=301)).isoformat()
    elif failure == "soc-unproven":
        report["soc"]["freshness_verified"] = False
    elif failure == "dry-run":
        report["mode"] = "dry-run"
    elif failure == "errors":
        report["errors"] = {"event": "not accepted"}
    elif failure == "missing-import":
        report["prices"]["import_verified"] = False
    elif failure == "price-coverage":
        report["prices"]["control_coverage"]["control_complete"] = False
    elif failure == "stale-report":
        report["checked_at_utc"] = (NOW - timedelta(seconds=451)).isoformat()
    elif failure == "proof-soc":
        report["soc"]["freshness_evidence"]["live_soc_percent"] = 54
    elif failure == "proof-time":
        report["soc"]["freshness_evidence"]["read_completed_at_utc"] = (NOW + timedelta(seconds=16)).isoformat()
    elif failure == "proof-power":
        report["soc"]["freshness_evidence"]["live_power_w"] = 100001
    elif failure == "control-out-of-range":
        files[name]["ac_charge"][0] = 1.1
    elif failure == "discharge-fraction":
        files[name]["discharge_allowed"][0] = .5
    else:
        report["event"]["version"] = "../secret"
    evidence, status = inspect(artifacts)
    assert status == 1 and not evidence["accepted"]


def test_waiting_is_not_acceptance_and_must_match_prices(artifacts):
    _, _, files = artifacts
    files["sync-report.json"]["event"] = {"status": "waiting-publication"}
    files["sync-state.json"]["events"] = {}
    files["sync-report.json"]["prices"]["control_coverage"]["control_complete"] = False
    files["prices.json"]["data"].pop("2026-10-30T01:00:00+00:00")
    evidence, status = inspect(artifacts)
    assert status == 2 and not evidence["accepted"]
    files["prices.json"]["data"]["2026-10-30T01:00:00+00:00"] = {PRICE_KEY: .0003}
    assert inspect(artifacts)[1] == 1


def test_active_writer_cannot_be_misread_as_completed_plan(artifacts):
    import fcntl
    folder, _, _ = artifacts
    inspect(artifacts)
    with (folder / "sync.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        evidence, status = acceptance(artifacts[1], now=NOW)
    assert status == 1 and "in progress" in evidence["reason"]


def test_missing_output_does_not_create_files(tmp_path):
    assert acceptance({"output": {"directory": str(tmp_path / "absent")}}, now=NOW)[1] == 1
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("flag", ["--write-eos", "--refresh-source"])
def test_cli_rejects_mutating_flags_without_health_writes(tmp_path, monkeypatch, flag):
    config = tmp_path / "config.toml"
    config.write_text("[output]\ndirectory='" + str(tmp_path) + "'\n")
    monkeypatch.setattr(sys, "argv", ["eos-pv-helper", "doctor", "--config", str(config), flag])
    assert main() == 1
    assert list(tmp_path.iterdir()) == [config]

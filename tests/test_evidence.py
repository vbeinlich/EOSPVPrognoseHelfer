"""Synthetic complete sync cycles; optimize HTTP is mocked, never executed."""

import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import test_sync

from eos_pv_helper import evidence
from eos_pv_helper.doctor import acceptance, snapshot_acceptance
from eos_pv_helper.historical import prepare, unpack, validate
from eos_pv_helper.storage import atomic_json


def build_case(config, monkeypatch):
    case = test_sync.sync_case.__wrapped__(config, monkeypatch)
    test_sync.configure_verified_evcc(case)
    config["evidence"] = {"enabled": True}
    original = case["http"]
    def http(url, **kwargs):
        value = original(url, **kwargs)
        if url.endswith("/v1/optimize"):
            value["start_solution_datetime"] = case["now"].replace(minute=0, second=0).isoformat()
        return value
    case["http"] = http
    def pv_runner(*args, **kwargs):
        case["pv_calls"] = case.get("pv_calls", 0) + 1
        series = case["series"]["pvforecast_ac_power"]
        payload = {"data": {key: {"pvforecast_ac_power": value} for key, value in series.items()}}
        report = {"count": len(series), "checked_at_utc": case["now"].isoformat(),
                  "source_fetched_at_utc": case["now"].isoformat(), "source_max_age_seconds": 3600,
                  "start_utc": min(series), "end_exclusive_utc": (
                      datetime.fromisoformat(max(series))+timedelta(minutes=15)).isoformat(),
                  "import_verified": kwargs.get("write_eos", False)}
        root = Path(config["output"]["directory"])
        atomic_json(root / "forecast.json", payload)
        atomic_json(root / "report.json", report)
        return payload, report
    case["pv_runner"] = pv_runner
    return case


@pytest.fixture
def case(config, monkeypatch):
    value = build_case(config, monkeypatch)
    monkeypatch.setenv("DRY_RUN", "false")
    return value


def archive(case):
    files = list((Path(case["config"]["output"]["directory"]) / evidence.DIRECTORY).glob("*.zip"))
    assert len(files) == 1
    return files[0]


def tick(case):
    return test_sync.tick(case, write_eos=True)


def test_success_archives_exact_originals_and_doctor_accepts(case):
    report = tick(case)
    assert report["event"]["status"] == "succeeded" and report["errors"] == {}
    assert report["evidence"]["status"] == "archived"
    path = archive(case)
    assert path.stat().st_mode & 0o777 == 0o400
    manifest, files = unpack(path.read_bytes())
    assert len(files) == 7
    assert manifest["schema_version"] == 2
    assert manifest["producer"]["contract"] == "eos-pv-helper/automatic-evidence-v1"
    root = Path(case["config"]["output"]["directory"])
    for name, raw in files.items():
        if name != "sync-report.json":
            assert raw == (root / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == manifest["files"][name]
    # Original report was durable before archive-status metadata was appended.
    assert "evidence" not in json.loads(files["sync-report.json"])
    result, status = snapshot_acceptance(path, now=case["now"]+timedelta(days=2))
    assert status == 0 and result["accepted"] and not result["current_freshness_verified"]
    assert acceptance(case["config"], now=case["now"])[1] == 0
    assert len(test_sync.writes(case, "POST")) == 1


def test_waiting_does_not_create_archive_or_reconstruct_past_claims(case):
    local = case["now"].astimezone(test_sync.ZoneInfo("Europe/Berlin"))
    cutoff = (local.replace(hour=0, minute=0, second=0)+timedelta(days=1)).timestamp()
    case["evcc"]["forecast"]["grid"] = [r for r in case["evcc"]["forecast"]["grid"] if r[0] < cutoff]
    assert tick(case)["event"] == {"status": "waiting-publication"}
    assert not test_sync.writes(case, "POST")
    assert not (Path(case["config"]["output"]["directory"]) / evidence.DIRECTORY).exists()


def test_later_waiting_and_new_inputs_do_not_modify_history(case):
    first = tick(case)
    path = archive(case)
    before = path.read_bytes(), path.stat().st_mtime_ns
    local = case["now"].astimezone(test_sync.ZoneInfo("Europe/Berlin"))
    cutoff = (local.replace(hour=0, minute=0, second=0)+timedelta(days=1)).timestamp()
    case["evcc"]["forecast"]["grid"] = [r for r in case["evcc"]["forecast"]["grid"] if r[0] < cutoff]
    case["now"] += timedelta(seconds=60)
    assert tick(case)["event"]["status"] == "waiting-publication"
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    result, emitted = prepare(path.parent.parent, case["config"], historical=path.read_bytes(),
                              event_version=first["event"]["version"], now=case["now"])
    assert result["accepted"] and emitted == before[0]
    assert len(test_sync.writes(case, "POST")) == 1


def test_restart_idempotence_and_disabled_migration_do_not_backfill(case):
    tick(case)
    path = archive(case)
    before = path.read_bytes(), path.stat().st_mtime_ns
    case["config"] = copy.deepcopy(case["config"])
    case["now"] += timedelta(seconds=1)
    assert tick(case)["evidence"]["status"] == "archived"
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    # An operator's separately removed archive cannot be rebuilt from today's files.
    path.unlink()
    report = tick(case)
    assert report["event"]["status"] == "succeeded"
    assert report["evidence"]["status"] == "evidence_missing"
    assert len(test_sync.writes(case, "POST")) == 1
    assert acceptance(case["config"], now=case["now"])[1] == 1


@pytest.mark.parametrize("failure", ["missing", "soc", "pv", "price", "privacy"])
def test_missing_mixed_or_private_inputs_never_change_dispatch_or_create_evidence(case, failure):
    original = case["http"]
    root = Path(case["config"]["output"]["directory"])
    changed = False
    def http(url, **kwargs):
        nonlocal changed
        result = original(url, **kwargs)
        # Last measurement readback immediately precedes evidence capture.
        if "/v1/measurement/series?" in url and not changed and (root / "prices.json").exists():
            changed = True
            if failure == "missing":
                (root / "forecast.json").unlink()
            else:
                name = {"soc": "soc.json", "pv": "forecast.json", "price": "prices.json", "privacy": "report.json"}[failure]
                value = json.loads((root / name).read_bytes())
                if failure == "soc":
                    value["percent"] = 12
                elif failure == "pv":
                    for row in value["data"].values():
                        row["pvforecast_ac_power"] = 9999
                elif failure == "price":
                    next(iter(value["data"].values()))[test_sync.PRICE_KEY] = .0009
                else:
                    value["token"] = "SYNTHETIC-SECRET-CANARY"
                atomic_json(root / name, value)
        return result
    case["http"] = http
    report = tick(case)
    assert report["event"]["status"] == "succeeded"
    assert report["errors"] == {} and report["evidence"]["status"] == "evidence_missing"
    assert "CANARY" not in json.dumps(report["evidence"])
    assert not list((root / evidence.DIRECTORY).glob("*.zip"))
    assert len(test_sync.writes(case, "POST")) == 1


def test_inputs_are_frozen_before_post_not_reread_after_it(case):
    original = case["http"]
    root = Path(case["config"]["output"]["directory"])
    def http(url, **kwargs):
        value = original(url, **kwargs)
        if url.endswith("/v1/optimize"):
            for name in evidence.INPUTS:
                atomic_json(root / name, {"new_cycle": True})
        return value
    case["http"] = http
    assert tick(case)["evidence"]["status"] == "archived"
    manifest, files = unpack(archive(case).read_bytes())
    assert all(b"new_cycle" not in raw for raw in files.values())
    assert validate(manifest, files, now=case["now"])["accepted"]


def test_ready_file_recovered_after_crash_without_new_post_or_inputs(case, monkeypatch):
    real_link = evidence.os.link
    def crash(source, target):
        if str(target).endswith(".zip"):
            raise SystemExit("synthetic process interruption")
        return real_link(source, target)
    with monkeypatch.context() as fault:
        fault.setattr(evidence.os, "link", crash)
        with pytest.raises(SystemExit):
            tick(case)
    root = Path(case["config"]["output"]["directory"])
    ready = next((root / evidence.DIRECTORY / ".pending").glob("*.ready"))
    original = ready.read_bytes()
    # New data cannot contaminate recovery: complete ready bytes are the sole input.
    for name in evidence.INPUTS:
        atomic_json(root / name, {"later_cycle": True})
    case["now"] += timedelta(seconds=1)
    assert tick(case)["evidence"]["status"] == "archived"
    assert archive(case).read_bytes() == original
    assert len(test_sync.writes(case, "POST")) == 1
    assert not ready.exists()


@pytest.mark.parametrize("boundary", ["uncertain", "solution", "report"])
def test_crash_before_complete_ready_never_retries_or_fabricates_success(case, monkeypatch, boundary):
    import eos_pv_helper.sync as sync
    real = sync.atomic_json
    def crash(path, value):
        path = Path(path)
        real(path, value)
        if ((boundary == "uncertain" and path.name == "sync-state.json"
             and any(c["status"] == "uncertain" for c in value["events"].values()))
            or (boundary == "solution" and path.name.startswith("solution-"))
            or (boundary == "report" and path.name == "sync-report.json")):
            raise SystemExit("synthetic process interruption")
    with monkeypatch.context() as fault:
        fault.setattr(sync, "atomic_json", crash)
        with pytest.raises(SystemExit):
            tick(case)
    posts = len(test_sync.writes(case, "POST"))
    report = tick(case)
    assert len(test_sync.writes(case, "POST")) == posts
    root = Path(case["config"]["output"]["directory"])
    assert not list((root / evidence.DIRECTORY).glob("*.zip"))
    if boundary == "report":
        assert report["evidence"]["status"] == "evidence_missing"
    else:
        assert report["event"]["status"] == "uncertain"


def test_two_processes_publish_only_one_archive_and_one_dispatch(case):
    import multiprocessing
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    original = case["http"]
    def http(url, **kwargs):
        if kwargs.get("method") == "POST":
            queue.put("post")
        return original(url, **kwargs)
    case["http"] = http
    def worker():
        queue.put(tick(case)["evidence"]["status"])
    workers = [context.Process(target=worker) for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(15)
            assert worker.exitcode == 0
        assert sorted(queue.get(timeout=1) for _ in range(3)) == ["archived", "archived", "post"]
        assert snapshot_acceptance(archive(case), now=case["now"])[1] == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(2)
        queue.close()


@pytest.mark.parametrize("instant", ["2026-03-28T13:05:00+00:00", "2026-10-24T13:05:00+00:00"])
def test_dst_delivery_days_archive_real_price_intervals(case, instant):
    case["now"] = datetime.fromisoformat(instant)
    start = case["now"].replace(hour=0, minute=0)-timedelta(hours=3)
    case["evcc"]["forecast"]["grid"] = [[int(start.timestamp())+i*900, int(start.timestamp())+(i+1)*900, .3]
                                         for i in range(300)]
    for key in case["series"]:
        case["series"][key] = {(start+timedelta(minutes=15*i)).isoformat(): 1000 if key == "pvforecast_ac_power" else .00008
                              for i in range(300)}
    report = tick(case)
    assert report["evidence"]["status"] == "archived"
    assert report["event"]["delivery_intervals"] in (92, 100)
    assert snapshot_acceptance(archive(case), now=case["now"]+timedelta(days=2))[1] == 0


def test_multiple_real_event_versions_remain_separate_and_immutable(case):
    tick(case)
    first = archive(case)
    before = first.read_bytes(), first.stat().st_mtime_ns
    local = case["now"].astimezone(test_sync.ZoneInfo("Europe/Berlin"))
    tomorrow = (local.replace(hour=0, minute=0, second=0)+timedelta(days=1)).timestamp()
    next(row for row in case["evcc"]["forecast"]["grid"] if row[0] == tomorrow)[2] = .42
    case["now"] += timedelta(seconds=1)
    assert tick(case)["evidence"]["status"] == "archived"
    paths = list(first.parent.glob("*.zip"))
    assert len(paths) == 2 and before == (first.read_bytes(), first.stat().st_mtime_ns)
    assert all(snapshot_acceptance(path, now=case["now"])[1] == 0 for path in paths)
    assert len(test_sync.writes(case, "POST")) == 2


def test_opt_in_does_not_backfill_an_earlier_success(case):
    case["config"]["evidence"]["enabled"] = False
    assert "evidence" not in tick(case)
    root = Path(case["config"]["output"]["directory"])
    assert not (root / evidence.DIRECTORY).exists()
    case["config"]["evidence"]["enabled"] = True
    assert tick(case)["evidence"]["status"] == "evidence_missing"
    assert not (root / evidence.DIRECTORY).exists()
    assert len(test_sync.writes(case, "POST")) == 1


def test_archive_io_failure_is_diagnostic_and_recoverable_without_reoptimization(case, monkeypatch):
    link = evidence.os.link
    def fail(source, target):
        if str(target).endswith(".zip"):
            raise OSError("synthetic I/O fault")
        return link(source, target)
    with monkeypatch.context() as fault:
        fault.setattr(evidence.os, "link", fail)
        report = tick(case)
    assert report["event"]["status"] == "succeeded" and report["errors"] == {}
    assert report["evidence"]["status"] == "evidence_missing"
    root = Path(case["config"]["output"]["directory"])
    assert json.loads((root / "health.json").read_bytes())["ok"] is False
    assert tick(case)["evidence"]["status"] == "archived"
    assert len(test_sync.writes(case, "POST")) == 1


def test_disk_full_does_not_retry_dispatch_or_publish_partial_archive(case, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(evidence.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    report = tick(case)
    assert report["event"]["status"] == "succeeded"
    assert report["evidence"]["reason"] == "archive_insufficient_disk_space"
    assert len(test_sync.writes(case, "POST")) == 1
    assert not list((Path(case["config"]["output"]["directory"]) / evidence.DIRECTORY).glob("*.zip"))


def test_corrupt_final_archive_is_never_overwritten(case):
    tick(case)
    path = archive(case)
    path.chmod(0o600)  # Simulate external tampering with synthetic data only.
    path.write_bytes(b"synthetic corrupted archive")
    before = path.read_bytes(), path.stat().st_mtime_ns
    assert tick(case)["evidence"]["status"] == "evidence_missing"
    assert before == (path.read_bytes(), path.stat().st_mtime_ns)
    assert len(test_sync.writes(case, "POST")) == 1
    assert acceptance(case["config"], now=case["now"])[1] == 1


def test_corrupt_ready_is_not_promoted_or_reconstructed(case, monkeypatch):
    link = evidence.os.link
    def crash(source, target):
        if str(target).endswith(".zip"):
            raise SystemExit("synthetic interruption")
        return link(source, target)
    with monkeypatch.context() as fault:
        fault.setattr(evidence.os, "link", crash)
        with pytest.raises(SystemExit):
            tick(case)
    root = Path(case["config"]["output"]["directory"])
    ready = next((root / evidence.DIRECTORY / ".pending").glob("*.ready"))
    ready.chmod(0o600)
    ready.write_bytes(b"synthetic incomplete archive")
    report = tick(case)
    assert report["evidence_recovery"]["status"] == "evidence_missing"
    assert report["evidence"]["status"] == "evidence_missing"
    assert not list((root / evidence.DIRECTORY).glob("*.zip"))
    assert len(test_sync.writes(case, "POST")) == 1


def test_no_additional_api_calls_or_changed_dispatch_payload(case, config, monkeypatch, tmp_path):
    other_config = copy.deepcopy(config)
    other_config["output"]["directory"] = str(tmp_path / "other")
    other = build_case(other_config, monkeypatch)
    other["now"] = case["now"]
    other["evcc"]["forecast"]["grid"] = copy.deepcopy(case["evcc"]["forecast"]["grid"])
    other["config"]["evidence"]["enabled"] = False
    monkeypatch.setenv("DRY_RUN", "false")
    assert tick(case)["evidence"]["status"] == "archived"
    assert "evidence" not in tick(other)
    assert case["calls"] == other["calls"]


def test_input_capture_cannot_bypass_final_soc_freshness_check(case, monkeypatch):
    capture = evidence.capture_inputs
    def delayed(*args):
        value = capture(*args)
        case["now"] += timedelta(seconds=301)
        return value
    monkeypatch.setattr("eos_pv_helper.sync.capture_inputs", delayed)
    report = tick(case)
    assert "expired" in report["errors"]["event"]
    assert not test_sync.writes(case, "POST")
    assert not list((Path(case["config"]["output"]["directory"]) / evidence.DIRECTORY).glob("*.zip"))

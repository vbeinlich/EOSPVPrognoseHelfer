"""Synthetic orchestration contracts. Native subprocess coverage is separate."""

import copy
import fcntl
import json
from datetime import timedelta
from pathlib import Path

import pytest
from replay_worker_fixture import create

from eos_pv_helper import dashboard, historical
from eos_pv_helper import replay_contract as contract
from eos_pv_helper.replay_worker import Worker, snapshot
from eos_pv_helper.replay_worker_io import WorkerError, read, sha, write


@pytest.fixture
def case(tmp_path):
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    version, claimed, candidate = create(source)
    workspace = tmp_path / "replays"
    workspace.mkdir(mode=0o700)
    clock = [claimed-timedelta(seconds=1)]
    calls = []

    def runner(root, source_hash, lock_fd, **limits):
        calls.append((source_hash, limits))
        assert lock_fd >= 0
        solution = json.loads(read(root / "pending" / (source_hash+".solution")))
        plan = copy.deepcopy(json.loads(candidate)["plans"][0])
        if plan["source_solution_sha256"] != source_hash:
            # A second independently constructed synthetic day uses the same numbers.
            from eos_pv_helper import economics

            start = historical.timestamp(solution["start_solution_datetime"])
            plan.update(source_solution_sha256=source_hash, start_utc=start.isoformat(),
                        parameters_sha256=contract.digest(solution["parameters"]),
                        projection_sha256=contract.digest(economics.project(solution)))
            for i, slot in enumerate(plan["slots"]):
                slot.update(start_utc=(start+timedelta(hours=i)).isoformat(),
                            end_utc=(start+timedelta(hours=i+1)).isoformat())
            plan["summary"] = contract.summarize(plan["slots"], plan["usable_capacity_wh"])
            plan = contract.seal({k: v for k, v in plan.items() if k != "sha256"})
        metrics = {"reason": "verified", "wall_seconds": .01, "synthetic_runner": True}
        write(root / "pending" / (source_hash+".metrics.json"), contract.canonical(metrics))
        write(root / "pending" / (source_hash+".json"),
              contract.canonical(contract.catalog([plan])), immutable=True)
        return metrics

    worker = Worker(source, workspace, now=lambda: clock[0], runner=runner)
    return worker, source, workspace, clock, calls, version, claimed, candidate


def settle(case):
    worker, _, _, clock, _, _, claimed, _ = case
    worker.tick()
    clock[0] = claimed+timedelta(seconds=3)
    return worker.tick()


def jobs(worker):
    return list(worker.state()["jobs"].values())


def test_new_committed_plan_sidecar_dashboard_and_idempotence(case, tmp_path):
    worker, source, root, clock, calls, version, _, _ = case
    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
              for p in source.rglob("*") if p.is_file()}
    assert settle(case)["counts"]["verified"] == 1
    immutable = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                 for name in ("verified", "receipts") for p in (root / name).iterdir()}
    worker.tick()
    assert len(calls) == 1
    assert immutable == {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                         for name in ("verified", "receipts") for p in (root / name).iterdir()}
    site = tmp_path / "site"
    site.mkdir()
    assert dashboard.refresh(source, site, replay_file=root / "catalog.json")
    data = json.loads(dashboard.DATA_PATTERN.search((site / "index.html").read_text())[1])
    assert data["plans"][0]["version"] == version
    assert data["plans"][0]["rows"][0]["flow"]["proof"] == contract.PROOF
    assert before == {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                      for p in source.rglob("*") if p.is_file()}
    assert calls[0][1] == {"timeout": 90, "cpu_seconds": 30, "address_space_mb": 3072}


def test_two_regular_versions_append_and_keep_earlier_bytes(case):
    worker, source, root, clock, calls, _, _, _ = case
    settle(case)
    first = next((root / "verified").iterdir())
    first_bytes = first.read_bytes()
    _, claimed, _ = create(source, day=31)
    clock[0] = claimed+timedelta(seconds=1)
    worker.tick()
    clock[0] += timedelta(seconds=3)
    worker.tick()
    assert len(calls) == 2 and len(worker.catalog.load()["plans"]) == 2
    assert first.read_bytes() == first_bytes


def test_old_dates_never_automatically_backfilled(case):
    worker, _, root, clock, calls, _, claimed, _ = case
    clock[0] = claimed+timedelta(days=3)
    worker.tick()
    clock[0] += timedelta(seconds=10)
    worker.tick()
    assert not calls and not (root / "catalog.json").exists()


@pytest.mark.parametrize("failure", ["no-archive", "source-bytes", "claim", "archive-hash",
                                    "missing-input", "no-binding", "nonautomatic", "report"])
def test_invalid_inputs_never_start_native_job(case, failure):
    worker, source, root, _, calls, version, _, _ = case
    archive = source / "genetic-evidence" / (version+".zip")
    if failure == "no-archive":
        archive.unlink()
    elif failure == "source-bytes":
        with (source / ("solution-"+version+".json")).open("ab") as h:
            h.write(b" ")
    elif failure in ("claim", "report"):
        path = source / ("sync-state.json" if failure == "claim" else "sync-report.json")
        value = json.loads(path.read_bytes())
        target = value["events"][version] if failure == "claim" else value["event"]
        target["effective_tail_hours"] = 1
        path.write_text(json.dumps(value))
    else:
        manifest, files = historical.unpack(archive.read_bytes())
        if failure == "archive-hash":
            manifest["files"]["forecast.json"] = "a"*64
        elif failure == "missing-input":
            del files["soc.json"]
        elif failure == "nonautomatic":
            manifest.pop("producer")
        else:
            report = json.loads(files["sync-report.json"])
            report["event"].pop("request_binding")
            files["sync-report.json"] = json.dumps(report).encode()
            manifest["files"]["sync-report.json"] = sha(files["sync-report.json"])
        archive.write_bytes(historical.pack(manifest, files))
    settle(case)
    assert not calls and not (root / "catalog.json").exists()
    assert jobs(worker)[0]["status"] == ("retry_later" if failure == "no-archive" else "rejected")


def test_busy_original_writer_cannot_be_processed(case):
    worker, source, _, _, calls, _, _, _ = case
    with (source / "sync.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(WorkerError, match="source_busy"):
            worker.tick()
    assert not calls


def test_worker_exclusion(case):
    worker, _, root, _, calls, _, _, _ = case
    path = root / "state" / "worker.lock"
    with path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        assert worker.tick()["reason"] == "worker_lock_busy"
    assert not calls


def test_incomplete_retry_is_bounded_with_backoff(case):
    worker, source, _, clock, calls, version, _, _ = case
    (source / "genetic-evidence" / (version+".zip")).unlink()
    settle(case)
    assert jobs(worker)[0]["attempts"] == 1
    worker.tick()
    assert jobs(worker)[0]["attempts"] == 1
    for seconds in (61, 121, 10000):
        clock[0] += timedelta(seconds=seconds)
        worker.tick()
    job = jobs(worker)[0]
    assert job["attempts"] == 3 and job["status"] == "rejected"
    assert job["reason"] == "incomplete_archive_retry_exhausted" and not calls


def test_restart_after_completed_native_candidate_does_not_replay(case, monkeypatch):
    worker, source, root, clock, calls, _, _, _ = case
    original = worker.catalog.add

    class Interrupted(BaseException):
        pass

    monkeypatch.setattr(worker.catalog, "add", lambda *a: (_ for _ in ()).throw(Interrupted()))
    with pytest.raises(Interrupted):
        settle(case)
    restarted = Worker(source, root, now=lambda: clock[0], runner=worker.runner)
    restarted.catalog.add = original
    assert restarted.tick()["counts"]["verified"] == 1
    assert len(calls) == 1


def test_candidate_simulation_mismatch_rejected(case):
    worker, _, root, _, _, _, _, _ = case
    original = worker.runner

    def altered(*args, **kwargs):
        result = original(*args, **kwargs)
        path = root / "pending" / (args[1]+".json")
        value = json.loads(path.read_bytes())
        value["plans"][0]["replay"]["result"]["total_costs"] += 1
        path.chmod(0o600)
        path.write_text(json.dumps(value))
        return result

    worker.runner = altered
    assert settle(case)["counts"]["rejected"] == 1
    assert not (root / "catalog.json").exists()


def test_corrupt_catalog_preserves_last_valid_html(case, tmp_path):
    worker, source, root, _, _, _, _, _ = case
    settle(case)
    site = tmp_path / "site"
    site.mkdir()
    assert dashboard.refresh(source, site, replay_file=root / "catalog.json")
    before = json.loads(dashboard.DATA_PATTERN.search((site / "index.html").read_text())[1])
    (root / "catalog.json").write_text('{"truncated":')
    with pytest.raises(ValueError):
        worker.tick()
    assert not dashboard.refresh(source, site, replay_file=root / "catalog.json")
    after = json.loads(dashboard.DATA_PATTERN.search((site / "index.html").read_text())[1])
    assert before["plans"] == after["plans"] and after["update_error"]


def test_explicit_legacy_import_keeps_claim_unknown_and_import_file_unchanged(case, tmp_path):
    worker, source, root, _, calls, version, _, candidate = case
    value = json.loads((source / "sync-state.json").read_bytes())
    value["events"][version]["status"] = "uncertain"
    (source / "sync-state.json").write_text(json.dumps(value))
    path = tmp_path / "historical-sidecar.json"
    path.write_bytes(candidate)
    assert worker.import_sidecar(path)["historical_execution_proven"] is False
    assert path.read_bytes() == candidate and not calls
    assert json.loads((source / "sync-state.json").read_bytes())["events"][version]["status"] == "uncertain"
    receipt = json.loads(next((root / "receipts").iterdir()).read_bytes())
    assert receipt["admission"] == "explicit_import_native_model_only"


def test_original_readers_never_use_current_forecasts_and_symlinks_fail(case, monkeypatch):
    _, source, _, _, _, version, claimed, _ = case
    original = Path.open

    def denied(path, *args, **kwargs):
        assert path.name not in ("prices.json", "forecast.json", "soc.json", "config.toml")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    assert snapshot(source, version, claimed)[1]["input_binding_complete"]
    path = source / ("solution-"+version+".json")
    path.unlink()
    path.symlink_to(source / "sync-state.json")
    with pytest.raises(WorkerError):
        snapshot(source, version, claimed)


def test_corrupt_immutable_file_is_not_replaced(case):
    worker, _, root, _, calls, _, _, _ = case
    settle(case)
    path = next((root / "verified").iterdir())
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    before = (root / "catalog.json").read_bytes()
    with pytest.raises(ValueError):
        worker.tick()
    assert path.read_bytes() == b"corrupt" and len(calls) == 1
    assert (root / "catalog.json").read_bytes() == before


def test_concurrent_catalog_update_and_refresh_never_observe_partial_json(case, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    worker, source, root, clock, _, _, _, _ = case
    settle(case)
    _, claimed, _ = create(source, day=31)
    clock[0] = claimed+timedelta(seconds=1)
    worker.tick()
    clock[0] += timedelta(seconds=3)
    site = tmp_path / "site"
    site.mkdir()
    with ThreadPoolExecutor(max_workers=2) as pool:
        publish = pool.submit(worker.tick)
        observed = []
        for _ in range(30):
            value = contract.decode(read(root / "catalog.json"))
            observed.append(len(value["plans"]))
            assert dashboard.refresh(source, site, replay_file=root / "catalog.json")
        assert publish.result()["counts"]["verified"] == 2
    assert set(observed) <= {1, 2} and len(worker.catalog.load()["plans"]) == 2
    report = dashboard.prepare(dashboard.collect(source, replay_file=root / "catalog.json"))
    for days in ("1", "7", "30"):
        slots = report["ranges"].get(days, [])
        assert len({slot["start_utc"] for slot in slots}) == len(slots)


def test_missing_original_input_cannot_use_live_replacement(case):
    worker, source, root, _, calls, version, _, _ = case
    path = source / "genetic-evidence" / (version+".zip")
    manifest, files = historical.unpack(path.read_bytes())
    del files["forecast.json"]
    path.write_bytes(historical.pack(manifest, files))
    (source / "forecast.json").write_text('{"current":"NEVER-USE"}')
    settle(case)
    assert not calls and not (root / "catalog.json").exists()


def test_wrong_candidate_source_hash_is_rejected(case):
    worker, _, root, _, _, _, _, _ = case
    original = worker.runner

    def wrong(*args, **kwargs):
        metrics = original(*args, **kwargs)
        path = root / "pending" / (args[1]+".json")
        value = json.loads(path.read_bytes())
        plan = value["plans"][0]
        plan["source_solution_sha256"] = "a"*64
        plan = contract.seal({k: v for k, v in plan.items() if k != "sha256"})
        path.chmod(0o600)
        path.write_bytes(contract.canonical(contract.catalog([plan])))
        return metrics

    worker.runner = wrong
    assert settle(case)["counts"]["rejected"] == 1
    assert not (root / "catalog.json").exists()


def test_late_archive_commit_supersedes_incomplete_observation_without_stale_alarm(case):
    worker, source, _, clock, calls, version, _, _ = case
    archive = source / "genetic-evidence" / (version+".zip")
    raw = archive.read_bytes()
    archive.unlink()
    assert settle(case)["counts"]["retry_later"] == 1
    archive.write_bytes(raw)
    worker.tick()
    clock[0] += timedelta(seconds=3)
    counts = worker.tick()["counts"]
    assert counts["verified"] == 1 and counts["retry_later"] == counts["rejected"] == 0
    assert len(calls) == 1
    assert len(worker.state()["jobs"]) == 2  # Earlier observations remain auditable.


def test_repeated_parent_crashes_without_completed_candidate_are_bounded(case):
    worker, _, _, clock, calls, _, claimed, _ = case
    worker.tick()
    state = worker.state()
    job = next(iter(state["jobs"].values()))
    job.update(status="running", attempts=worker.retries, source_solution_sha256="a"*64)
    worker.save(state)
    clock[0] = claimed+timedelta(seconds=3)
    result = worker.tick()
    assert result["counts"]["rejected"] == 1 and not calls
    assert jobs(worker)[0]["reason"] == "interrupted_native_retry_exhausted"


def test_duplicate_current_claim_keys_block_before_replay(case):
    worker, source, _, _, calls, version, _, _ = case
    state = json.loads((source / "sync-state.json").read_bytes())
    claim = json.dumps(state["events"][version])
    duplicate = '{"events":{"'+version+'":'+claim+',"'+version+'":'+claim+'}}'
    (source / "sync-state.json").write_text(duplicate)
    with pytest.raises(ValueError, match="Duplicate JSON evidence key"):
        worker.tick()
    assert not calls


def test_historical_import_rejects_private_parameters_even_with_correct_hashes(case, tmp_path):
    worker, source, root, _, calls, version, _, candidate = case
    path = source / ("solution-"+version+".json")
    solution = json.loads(path.read_bytes())
    solution["parameters"]["token"] = "SYNTHETIC-PRIVATE-CANARY"
    raw = json.dumps(solution).encode()
    path.write_bytes(raw)
    plan = json.loads(candidate)["plans"][0]
    plan.update(source_solution_sha256=sha(raw), parameters_sha256=contract.digest(solution["parameters"]))
    plan = contract.seal({k: v for k, v in plan.items() if k != "sha256"})
    sidecar = tmp_path / "private-input-candidate.json"
    sidecar.write_bytes(contract.canonical(contract.catalog([plan])))
    with pytest.raises(ValueError, match="privacy guard"):
        worker.import_sidecar(sidecar)
    assert not calls and not (root / "catalog.json").exists()

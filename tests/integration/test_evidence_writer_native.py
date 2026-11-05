"""Actual sync writer -> v2 archive -> PR #27 native job -> dashboard, no search."""

import hashlib
import json
import multiprocessing
import os
import signal
from datetime import timedelta
from pathlib import Path

import pytest
from evidence_writer_synthetic import SyntheticEvent

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from eos_pv_helper import dashboard, economics, evidence, historical, replay_contract  # noqa: E402
from eos_pv_helper.replay_worker import Worker  # noqa: E402
from eos_pv_helper.storage import atomic_json  # noqa: E402

TEMPLATE = Path(__file__).parents[1] / "fixtures/replay-synthetic-solution.json"


@pytest.fixture(autouse=True)
def no_optimizer_or_network(monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from requests.sessions import Session

    def forbidden(*args, **kwargs):
        pytest.fail("No optimizer search, network or device actions in evidence writer integration")

    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)
    monkeypatch.setenv("DRY_RUN", "false")


def setup(tmp_path):
    source, workspace = tmp_path / "output", tmp_path / "replays"
    event = SyntheticEvent(source, TEMPLATE)
    atomic_json(source / "sync-state.json", {"events": {}})
    (source / "sync.lock").touch()
    workspace.mkdir(mode=0o700)
    clock = [event.now-timedelta(seconds=1)]
    worker = Worker(source, workspace, now=lambda: clock[0], settle_seconds=0)
    assert worker.tick()["counts"]["verified"] == 0
    return event, worker, clock


def test_regular_sync_commits_originals_then_real_native_worker_and_dashboard(tmp_path):
    event, worker, clock = setup(tmp_path)
    report = event.tick()
    assert report["errors"] == {} and report["evidence"]["status"] == "archived"
    assert event.model_calls == 1  # Native fixed controls in a mock HTTP response, no search.
    version = report["event"]["version"]
    archive = event.root / report["evidence"]["archive"]
    manifest, files = historical.unpack(archive.read_bytes())
    assert len(files) == 7 and historical.validate(manifest, files, now=event.now)["accepted"]
    for name, raw in files.items():
        assert hashlib.sha256(raw).hexdigest() == manifest["files"][name]
    raw = files["solution-"+version+".json"]
    assert raw == (event.root / ("solution-"+version+".json")).read_bytes()
    assert economics.project(json.loads(raw))["controls"]["ac_charge"][0] == .5
    originals = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                 for p in event.root.rglob("*") if p.is_file()}
    clock[0] = event.now+timedelta(seconds=3)
    assert worker.tick()["counts"]["verified"] == 1, worker.state()
    plan = worker.catalog.load()["plans"][0]
    replay_contract.validate(plan, raw, json.loads(raw))
    site = tmp_path / "site"
    site.mkdir()
    assert dashboard.refresh(event.root, site, replay_file=worker.root / "catalog.json")
    view = json.loads(dashboard.DATA_PATTERN.search((site / "index.html").read_text())[1])
    assert view["plans"][0]["rows"][0]["flow"]["proof"] == replay_contract.PROOF
    immutable = {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                 for name in ("verified", "receipts") for p in (worker.root / name).iterdir()}
    worker.tick()
    assert originals == {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                         for p in event.root.rglob("*") if p.is_file()}
    assert event.tick()["evidence"]["status"] == "archived" and event.model_calls == 1
    assert immutable == {str(p): (p.read_bytes(), p.stat().st_mtime_ns)
                         for name in ("verified", "receipts") for p in (worker.root / name).iterdir()}
    assert len([c for c in event.calls if c[0] == "POST"]) == 1


def test_two_regular_sync_versions_have_separate_immutable_archives_and_native_sidecars(tmp_path):
    event, worker, clock = setup(tmp_path)
    first = event.tick()
    clock[0] = event.now+timedelta(seconds=3)
    assert worker.tick()["counts"]["verified"] == 1
    archive = event.root / first["evidence"]["archive"]
    sidecar = next((worker.root / "verified").glob("*.json"))
    before = archive.read_bytes(), sidecar.read_bytes()
    event.now += timedelta(days=1)
    second = event.tick()
    assert second["evidence"]["status"] == "archived"
    assert second["event"]["version"] != first["event"]["version"]
    clock[0] = event.now+timedelta(seconds=3)
    assert worker.tick()["counts"]["verified"] == 2, worker.state()
    assert (archive.read_bytes(), sidecar.read_bytes()) == before
    assert event.model_calls == 2 and len(worker.catalog.load()["plans"]) == 2


def test_modified_saved_solution_bytes_are_rejected_before_native_job(tmp_path):
    event, worker, clock = setup(tmp_path)
    assert event.tick()["evidence"]["status"] == "archived"
    solution = next(event.root.glob("solution-*.json"))
    with solution.open("ab") as handle:
        handle.write(b" ")  # Same JSON value, different ORIGINAL bytes.

    def forbidden(*args, **kwargs):
        pytest.fail("Changed source bytes must be rejected before a native child is created")

    worker.runner = forbidden
    clock[0] = event.now+timedelta(seconds=3)
    assert worker.tick()["counts"]["rejected"] == 1
    assert list(worker.state()["jobs"].values())[0]["reason"] == "archive_original_or_claim_conflict"
    assert not (worker.root / "catalog.json").exists()


@pytest.mark.parametrize("boundary", ["before-ready", "after-ready"])
def test_real_sigkill_during_archive_write_never_reoptimizes_or_fills_missing_inputs(tmp_path, boundary):
    event, worker, clock = setup(tmp_path)

    def child():
        link = evidence.os.link

        def crash(source, target):
            if str(target).endswith(".ready"):
                if boundary == "after-ready":
                    link(source, target)
                os.kill(os.getpid(), signal.SIGKILL)
            return link(source, target)

        evidence.os.link = crash
        event.tick()

    process = multiprocessing.get_context("fork").Process(target=child)
    process.start()
    process.join(20)
    try:
        assert process.exitcode == -signal.SIGKILL
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
    assert not list((event.root / evidence.DIRECTORY).glob("*.zip"))
    solution = next(event.root.glob("solution-*.json"))
    original = solution.read_bytes()
    # Deliberately destroy current input caches; recovery has to use complete ready
    # bytes or explicitly report missing evidence. No old inputs may be rebuilt.
    for name in evidence.INPUTS:
        atomic_json(event.root / name, {"later_unrelated_tick": True})
    clock[0] = event.now+timedelta(seconds=3)
    assert worker.tick()["counts"]["retry_later"] == 1
    report = event.tick()
    assert report["event"]["status"] == "succeeded" and event.model_calls == 0
    assert not [call for call in event.calls if call[0] == "POST"]
    assert solution.read_bytes() == original
    if boundary == "after-ready":
        assert report["evidence"]["status"] == "archived"
        assert report["evidence_recovery"]["status"] == "recovered"
        clock[0] += timedelta(seconds=1)
        assert worker.tick()["counts"]["verified"] == 1, worker.state()
    else:
        assert report["evidence"]["status"] == "evidence_missing"
        assert not list((event.root / evidence.DIRECTORY).glob("*.zip"))
        assert not (worker.root / "catalog.json").exists()

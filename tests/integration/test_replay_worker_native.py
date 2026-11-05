"""Actual native subprocess and kernel timeout, using synthetic archives only."""

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from replay_worker_fixture import create

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from eos_pv_helper import economics_native, replay_contract, replay_export  # noqa: E402
from eos_pv_helper.replay_worker import Worker, native_job  # noqa: E402
from eos_pv_helper.replay_worker_io import WorkerError  # noqa: E402


def test_actual_committed_native_job_metrics_and_no_second_run(tmp_path):
    source, root = tmp_path / "source", tmp_path / "replays"
    root.mkdir(mode=0o700)
    version, claimed, _ = create(source)
    clock = [claimed-timedelta(seconds=1)]
    worker = Worker(source, root, now=lambda: clock[0])
    worker.tick()
    clock[0] = claimed+timedelta(seconds=3)
    result = worker.tick()
    assert result["counts"]["verified"] == 1, worker.state()
    catalog = worker.catalog.load()
    plan = catalog["plans"][0]
    raw = (source / ("solution-"+version+".json")).read_bytes()
    replay_contract.validate(plan, raw, json.loads(raw))
    receipt_path = next((root / "receipts").iterdir())
    before = receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns
    receipt = json.loads(before[0])
    assert receipt["metrics"]["wall_seconds"] > 0
    assert receipt["metrics"]["cpu_seconds"] > 0
    assert 0 < receipt["metrics"]["max_rss_kib"] < 768*1024
    assert receipt["eos_revision"] == economics_native.EOS_REVISION
    worker.tick()
    assert before == (receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns)


def test_real_native_result_mismatch_becomes_rejected(tmp_path):
    from eos_pv_helper import historical

    source, root = tmp_path / "source", tmp_path / "replays"
    root.mkdir(mode=0o700)
    version, claimed, _ = create(source)
    archive_path = source / "genetic-evidence" / (version+".zip")
    manifest, files = historical.unpack(archive_path.read_bytes())
    name = "solution-"+version+".json"
    solution = json.loads(files[name])
    solution["result"]["total_costs"] += .01
    raw = (json.dumps(solution)+"\n").encode()
    files[name] = raw
    import hashlib

    manifest["files"][name] = hashlib.sha256(raw).hexdigest()
    (source / name).write_bytes(raw)
    archive_path.write_bytes(historical.pack(manifest, files))
    worker = Worker(source, root, now=lambda: claimed+timedelta(seconds=3), settle_seconds=0)
    assert worker.tick(version=version)["counts"]["rejected"] == 1
    assert next(iter(worker.state()["jobs"].values()))["reason"] == "native_result_or_flow_mismatch"
    assert not (root / "catalog.json").exists()


def test_native_export_exactly_two_simulations_no_search_or_http(monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization, GeneticSimulation
    from requests.sessions import Session

    calls = []
    original = GeneticSimulation.simulate

    def observe(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("Native replay must not perform optimization, HTTP, or device actions")

    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)
    monkeypatch.setattr(GeneticSimulation, "simulate", observe)
    raw = (Path(__file__).parents[1] / "fixtures/replay-synthetic-solution.json").read_bytes()
    plan = replay_export.create_plan(raw)
    assert len(calls) == 2 and plan["engine"]["optimizer_invoked"] is False


def test_kernel_wall_timeout_is_rejected_and_child_reaped(tmp_path, monkeypatch):
    import os

    from eos_pv_helper import replay_worker

    real_popen = subprocess.Popen
    observed = []

    def deliberately_slow(args, **kwargs):
        assert args[args.index("--timeout")+1] == "1"
        assert args[args.index("--cpu-seconds")+1] == "1"
        assert args[args.index("--address-space-mb")+1] == "512"
        assert kwargs["pass_fds"]
        child = real_popen([sys.executable, "-c",
                            "import signal,time;signal.setitimer(signal.ITIMER_REAL,1);time.sleep(30)"],
                           **kwargs)
        observed.append(child)
        return child

    monkeypatch.setattr(replay_worker.subprocess, "Popen", deliberately_slow)
    fd = os.open(tmp_path / "lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with pytest.raises(WorkerError, match="native_timeout_or_resource_limit"):
            native_job(tmp_path, "a"*64, fd, timeout=1, cpu_seconds=1, address_space_mb=512)
    finally:
        os.close(fd)
    assert observed[0].poll() is not None


def test_killed_parent_keeps_child_lock_then_recovers_without_second_replay(tmp_path):
    import os
    import signal
    import time

    source, root = tmp_path / "source", tmp_path / "replays"
    root.mkdir(mode=0o700)
    _, claimed, _ = create(source)
    Worker(source, root, now=lambda: claimed-timedelta(seconds=1)).tick()
    sentinel = tmp_path / "child-pid"
    parent_code = r'''
import subprocess,sys
from datetime import datetime
from pathlib import Path
from eos_pv_helper.replay_worker import Worker
real=subprocess.Popen
sentinel=sys.argv[3]
def delayed(args,**kwargs):
    code="import os,time;from pathlib import Path;Path("+repr(sentinel)+").write_text(str(os.getpid()));time.sleep(3);from eos_pv_helper.replay_worker_job import main;raise SystemExit(main())"
    return real([sys.executable,'-B','-c',code,*args[4:]],**kwargs)
subprocess.Popen=delayed
worker=Worker(Path(sys.argv[1]),Path(sys.argv[2]),now=lambda:datetime.fromisoformat(sys.argv[4]))
worker.tick()
'''
    parent = subprocess.Popen([sys.executable, "-B", "-c", parent_code, str(source), str(root),
                               str(sentinel), (claimed+timedelta(seconds=3)).isoformat()],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    child_pid = None
    try:
        deadline = time.monotonic()+15
        while not sentinel.exists() and time.monotonic() < deadline:
            assert parent.poll() is None
            time.sleep(.05)
        assert sentinel.exists()
        child_pid = int(sentinel.read_text())
        parent.kill()
        parent.wait(timeout=5)

        def forbidden(*args, **kwargs):
            pytest.fail("Completed orphan child must be recovered without a second replay")

        restarted = Worker(source, root, now=lambda: claimed+timedelta(seconds=10), runner=forbidden)
        assert restarted.tick()["reason"] == "worker_lock_busy"
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            result = restarted.tick()
            if result.get("counts", {}).get("verified") == 1:
                break
            time.sleep(.1)
        assert result["counts"]["verified"] == 1
        assert len(restarted.catalog.load()["plans"]) == 1
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait()
        if child_pid is not None:
            try:
                os.killpg(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

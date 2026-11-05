"""Installer offline gates against a real native synthetic archive and worker."""

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest
from evidence_writer_synthetic import SyntheticEvent

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from eos_pv_helper.replay_worker import Worker  # noqa: E402

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location("unraid_verify", ROOT / "deploy/unraid-test/verify.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


@pytest.fixture
def case(tmp_path, monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from requests.sessions import Session

    def forbidden(*args, **kwargs):
        pytest.fail("No search or HTTP in the installer gate tests")

    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)
    monkeypatch.setenv("DRY_RUN", "false")
    source, backup, workspace = (tmp_path / name for name in ("source", "backup", "replays"))
    backup.mkdir(mode=0o700)
    workspace.mkdir(mode=0o700)
    event = SyntheticEvent(source, ROOT / "tests/fixtures/replay-synthetic-solution.json")
    (backup / "claims-before.json").write_text('{"events":{}}')
    (backup / "installed-at-utc").write_text((event.now-timedelta(seconds=1)).isoformat())
    assert event.tick()["evidence"]["status"] == "archived"
    return event, backup, workspace


def test_new_archive_gate_then_native_worker_gate_even_after_waiting_report(case):
    event, backup, workspace = case
    (event.root / "sync-report.json").write_text('{"event":{"status":"waiting-publication"}}')
    report = verify.archive(event.root, backup)
    assert report["status"] == "archive_accepted" and report["artifacts"] == 7
    (backup / "archive-accepted.json").write_text(json.dumps(report))
    worker = Worker(event.root, workspace, settle_seconds=0, now=lambda: event.now+timedelta(seconds=3))
    assert worker.tick(version=report["version"])["counts"]["verified"] == 1
    assert verify.worker(workspace, event.root, backup)["native_flows_verified"]


@pytest.mark.parametrize("failure", ["old-claim", "before-install", "corrupt-archive"])
def test_archive_gate_does_not_accept_history_or_corrupt_bytes(case, failure):
    event, backup, _ = case
    if failure == "old-claim":
        (backup / "claims-before.json").write_bytes((event.root / "sync-state.json").read_bytes())
    elif failure == "before-install":
        (backup / "installed-at-utc").write_text((event.now+timedelta(seconds=1)).isoformat())
    else:
        archive = next((event.root / "genetic-evidence").glob("*.zip"))
        archive.chmod(0o600)
        archive.write_bytes(b"synthetic corrupted archive")
    with pytest.raises(ValueError):
        verify.archive(event.root, backup)


def test_worker_gate_rechecks_original_archive_binding_before_publisher_enable(case):
    event, backup, workspace = case
    report = verify.archive(event.root, backup)
    (backup / "archive-accepted.json").write_text(json.dumps(report))
    worker = Worker(event.root, workspace, settle_seconds=0, now=lambda: event.now+timedelta(seconds=3))
    assert worker.tick(version=report["version"])["counts"]["verified"] == 1
    report["archive_sha256"] = "0"*64
    (backup / "archive-accepted.json").write_text(json.dumps(report))
    with pytest.raises(ValueError):
        verify.worker(workspace, event.root, backup)


def test_activation_watermark_includes_install_gap_but_existing_state_is_never_reset(case):
    event, backup, workspace = case
    first = verify.init_worker(workspace, event.root, backup)
    state_file = workspace / "state/status.json"
    before = state_file.read_bytes()
    (backup / "installed-at-utc").write_text((event.now-timedelta(days=30)).isoformat())
    assert verify.init_worker(workspace, event.root, backup) == first
    assert state_file.read_bytes() == before
    worker = Worker(event.root, workspace, settle_seconds=0, now=lambda: event.now+timedelta(seconds=3))
    assert worker.tick()["counts"]["verified"] == 1  # Automatic, no historical --version bypass.

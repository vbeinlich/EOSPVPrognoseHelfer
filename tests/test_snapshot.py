import hashlib
import io
import json
import sys
import zipfile
from datetime import timedelta

import pytest

# Share only synthetic fixtures; no captured private installation data in tests.
import test_doctor as doctor_fixtures
from doctor_snapshot import export
from test_doctor import NOW, inspect

from eos_pv_helper.app import main
from eos_pv_helper.doctor import acceptance, snapshot_acceptance


@pytest.fixture
def artifacts(tmp_path):
    return doctor_fixtures.artifacts.__wrapped__(tmp_path)


def bundle(artifacts, *, captured=NOW, mutate=None):
    directory, _, _ = artifacts
    inspect(artifacts)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
    raw = export(directory, clock=lambda: captured)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()}
    if mutate:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files = {i.filename: archive.read(i.filename) for i in archive.infolist()}
        mutate(files)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for name, value in files.items():
                archive.writestr(name, value)
        raw = stream.getvalue()
    path = directory / "private-export.zip"
    path.write_bytes(raw)
    return path


def test_legacy_snapshot_is_incomplete_without_original_soc_and_pv(artifacts):
    path = bundle(artifacts)
    evidence, status = snapshot_acceptance(path, now=NOW+timedelta(days=1))
    assert status == 1 and not evidence["accepted"]
    assert evidence["evidence_mode"] == "historical_snapshot"
    assert evidence["current_freshness_verified"] is False
    assert "incomplete" in evidence["reason"]
    # Normal live validation keeps the original strict freshness boundary.
    assert acceptance(artifacts[1], now=NOW+timedelta(days=1))[1] == 1


@pytest.mark.parametrize("failure", ["hash", "future", "stale-at-capture", "undeclared", "traversal",
    "manifest-hash-map", "weak-limit", "missing-proof"])
def test_corrupt_or_invalid_capture_is_rejected(artifacts, failure):
    def change(files):
        manifest = json.loads(files["snapshot.json"])
        if failure == "hash":
            files["prices.json"] += b" "
        elif failure == "future":
            manifest["captured_at_utc"] = (NOW+timedelta(days=2)).isoformat()
        elif failure == "stale-at-capture":
            manifest["captured_at_utc"] = (NOW+timedelta(seconds=301)).isoformat()
        elif failure == "undeclared":
            files["secret.txt"] = b"must never read this"
        elif failure == "traversal":
            files["../sync-report.json"] = files.pop("sync-report.json")
        elif failure == "manifest-hash-map":
            manifest["files"].pop("prices.json")
        elif failure == "weak-limit":
            manifest["validation_constraints"]["max_age_seconds"] = 301
        else:
            report = json.loads(files["sync-report.json"])
            report["soc"]["freshness_verified"] = False
            files["sync-report.json"] = json.dumps(report).encode()
            manifest["files"]["sync-report.json"] = hashlib.sha256(files["sync-report.json"]).hexdigest()
        files["snapshot.json"] = json.dumps(manifest).encode()
    path = bundle(artifacts, mutate=change)
    assert snapshot_acceptance(path, now=NOW+timedelta(days=1))[1] == 1


def test_export_preserves_configured_stricter_limits_without_config_or_secrets(artifacts):
    directory, _, _ = artifacts
    inspect(artifacts)
    settings = {"soc": {"max_age_seconds": 60, "max_abs_power_w": 9000},
                "evcc": {"token_file": "/run/secrets/do-not-read"}, "private_key": "never-export"}
    raw = export(directory, config=settings, clock=lambda: NOW)
    assert b"never-export" not in raw
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest = json.loads(archive.read("snapshot.json"))
        assert manifest["validation_constraints"] == {"max_age_seconds": 60, "max_abs_power_w": 9000}
        assert "evcc" not in manifest and "private_key" not in manifest


def test_export_does_not_wait_for_or_interrupt_active_sync(artifacts):
    import fcntl
    folder, _, _ = artifacts
    inspect(artifacts)
    with (folder / "sync.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with pytest.raises(ValueError, match="in progress"):
            export(folder)


def test_cli_historical_check_does_not_require_or_read_live_configuration(artifacts, monkeypatch, capsys):
    path = bundle(artifacts)
    monkeypatch.setattr(sys, "argv", ["eos-pv-helper", "doctor", "--snapshot", str(path)])
    assert main() == 1
    assert json.loads(capsys.readouterr().out)["current_freshness_verified"] is False


@pytest.mark.parametrize("flag", ["--write-eos", "--refresh-source"])
def test_cli_rejects_writing_or_refreshing_while_inspecting_snapshot(artifacts, monkeypatch, flag):
    path = bundle(artifacts)
    monkeypatch.setattr(sys, "argv", ["eos-pv-helper", "doctor", "--snapshot", str(path), flag])
    assert main() == 1

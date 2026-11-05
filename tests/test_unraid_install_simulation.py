"""Execute real install/rollback Bash with a closed fake daemon in tmpfs only.

Normal CI/host pytest skips this module. The explicit isolated container gate
supplies EMS_INSTALL_SIMULATION_ONLY=1 and fresh /mnt, /app, /output tmpfs mounts.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from test_unraid_test_prepare import TAG, synthetic

ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(os.environ.get("EMS_INSTALL_SIMULATION_ONLY") != "1",
                                reason="Requires explicit disposable tmpfs installer simulation")


def fixture(tmp_path, monkeypatch):
    # Never delete or emulate anything in a real host/NAS /mnt directory.
    assert any(" /mnt " in line and " - tmpfs " in line
               for line in Path("/proc/self/mountinfo").read_text().splitlines())
    base = Path("/mnt/user/appdata")
    if base.exists():
        shutil.rmtree(base)
    output = base / "eos-pv-helper/output"
    output.mkdir(parents=True)
    backup_root = base / "ems-dashboard-review/backup"
    backup_root.mkdir(parents=True)
    rollback_tar = backup_root / "eos-pv-helper-rollback-e1c47a73.tar"
    rollback_tar.write_bytes(b"synthetic rollback image only")
    config = base / "eos-pv-helper/config.toml"
    config.write_bytes(b'''[output]\ndirectory="/output"\n[prices]\nenabled=true\n[evcc]\ntoken_file="/run/secrets/evcc"\n[trigger]\nenabled=true\nrun_enabled=true\n''')
    config.chmod(0o600)
    Path("/app/config.toml").write_bytes(config.read_bytes())
    Path("/run/secrets/evcc").write_bytes(b"PRIVATE-SYNTHETIC-KEY")
    initial_claim = b'{"events":{"old":{"status":"succeeded"}}}\n'
    for root in (output, Path("/output")):
        (root / "sync-state.json").write_bytes(initial_claim)
        (root / "sync.lock").touch()
    info, _ = synthetic()
    info.update(Name="/eos-pv-helper", State={"Running": True})
    info["Image"] = "sha256:e1c47a73e80272fd4fae9653d02ff9b993e894b4e6d39495e49b6fbd93f3495d"
    info["Config"]["WorkingDir"] = "/app"
    info["HostConfig"]["Binds"] = [str(config)+":/app/config.toml:ro", str(output)+":/output:rw",
                                    "/private/keys:/run/secrets:ro"]
    info["Mounts"] = info["Mounts"][:3]
    info["Mounts"][0]["Source"], info["Mounts"][1]["Source"] = str(config), str(output)
    helper_id = "sha256:"+"7"*64
    state_path = tmp_path / "engine.json"
    state_path.write_text(json.dumps({"containers": {info["Id"]: info}, "old_id": info["Id"],
        "helper_id": helper_id, "events": [], "output": str(output), "config": str(config)}))
    monkeypatch.setenv("EMS_FAKE_ENGINE", str(state_path))
    commands = tmp_path / "bin"
    commands.mkdir()
    for name in ("docker", "curl"):
        path = commands / name
        path.write_text("#!/bin/sh\nexec python "+str(ROOT / "tests/unraid_install_fake_engine.py")+" "+name+' "$@"\n')
        path.chmod(0o755)
    sleep = commands / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    monkeypatch.setenv("PATH", str(commands)+":"+os.environ["PATH"])
    package = tmp_path / "package"
    (package / "tools").mkdir(parents=True)
    for path in (ROOT / "deploy/unraid-test").glob("*"):
        if path.is_file():
            shutil.copyfile(path, package / "tools" / path.name)
    (package / "helper.tar").write_bytes(b"synthetic helper image")
    (package / "images.env").write_text("\n".join([
        "HELPER_TAG="+TAG, "HELPER_CONFIG_ID="+helper_id, "HELPER_LOCAL_ID="+helper_id,
        "HELPER_TAR=helper.tar", "ROLLBACK_SHA256="+hashlib.sha256(rollback_tar.read_bytes()).hexdigest()])+"\n")
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest()+"  "+p.relative_to(package).as_posix()
              for p in sorted(package.rglob("*")) if p.is_file()]
    (package / "SHA256SUMS").write_text("\n".join(hashes)+"\n")
    def run(*args):
        result = subprocess.run(["bash", str(package / "tools/unraid-test.sh"), *args],
                                text=True, capture_output=True, timeout=30)
        assert "SYNTHETIC-CANARY" not in result.stdout+result.stderr
        assert "PRIVATE-SYNTHETIC-KEY" not in result.stdout+result.stderr
        return result
    return run, state_path, config, output, backup_root, initial_claim


def test_real_install_and_manual_rollback_preserve_config_env_mounts_and_new_claims(tmp_path, monkeypatch):
    run, engine, config, output, backups, claims = fixture(tmp_path, monkeypatch)
    before = config.read_bytes()
    installed = run("install")
    assert installed.returncode == 0, installed.stderr
    state = json.loads(engine.read_bytes())
    assert state["events"].count("term-outside-dispatch") == 1
    assert not state["containers"]["1"*64]["State"]["Running"]
    assert state["containers"]["2"*64]["State"]["Running"]
    backup = next(backups.glob("ems-v11-*"))
    assert (backup / "config-original.toml").read_bytes() == before
    assert backup.stat().st_mode & 0o777 == 0o700 and backup.stat().st_uid == 0
    assert (backup / "container-inspect.json").stat().st_mode & 0o777 == 0o600
    expected = tomllib.loads(before.decode())
    expected["evidence"] = {"enabled": True}
    assert tomllib.loads(config.read_text()) == expected
    assert (output / "sync-state.json").read_bytes() == claims
    # New, legitimate state AFTER replacement must survive rollback too.
    later = b'{"events":{"old":{"status":"succeeded"},"new":{"status":"succeeded"}}}\n'
    (output / "sync-state.json").write_bytes(later)
    result = run("rollback", str(backup))
    assert result.returncode == 0, result.stderr
    state = json.loads(engine.read_bytes())
    assert len(state["containers"]) == 1 and state["containers"]["1"*64]["State"]["Running"]
    assert config.read_bytes() == before and (output / "sync-state.json").read_bytes() == later


@pytest.mark.parametrize("failure", ["EMS_FAIL_CREATE", "EMS_CREATE_ACK_LOST", "EMS_FAIL_START", "EMS_DRIFT_NEW_RUNTIME"])
def test_create_or_start_error_restores_old_helper_without_resetting_output(tmp_path, monkeypatch, failure):
    run, engine, config, output, _, claims = fixture(tmp_path, monkeypatch)
    before = config.read_bytes()
    monkeypatch.setenv(failure, "1")
    result = run("install")
    assert result.returncode != 0
    state = json.loads(engine.read_bytes())
    assert len(state["containers"]) == 1 and state["containers"]["1"*64]["State"]["Running"]
    assert config.read_bytes() == before and (output / "sync-state.json").read_bytes() == claims


def test_missing_secret_backup_stops_before_image_load_or_container_stop(tmp_path, monkeypatch):
    run, engine, config, output, _, claims = fixture(tmp_path, monkeypatch)
    Path("/run/secrets/evcc").unlink()
    before = config.read_bytes()
    result = run("install")
    assert result.returncode != 0 and not json.loads(engine.read_bytes())["events"]
    assert config.read_bytes() == before and (output / "sync-state.json").read_bytes() == claims


def test_config_changed_during_stop_is_preserved_and_old_helper_restarted(tmp_path, monkeypatch):
    run, engine, config, _, _, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setenv("EMS_CHANGE_CONFIG_ON_STOP", "1")
    result = run("install")
    assert result.returncode != 0
    assert b'operator_change = "keep"' in config.read_bytes()
    assert json.loads(engine.read_bytes())["containers"]["1"*64]["State"]["Running"]


def test_manual_rollback_refuses_to_overwrite_a_later_operator_config_change(tmp_path, monkeypatch):
    run, engine, config, _, backups, _ = fixture(tmp_path, monkeypatch)
    assert run("install").returncode == 0
    backup = next(backups.glob("ems-v11-*"))
    with config.open("ab") as handle:
        handle.write(b'\noperator_change = "keep"\n')
    result = run("rollback", str(backup))
    assert result.returncode != 0 and b'operator_change = "keep"' in config.read_bytes()
    assert json.loads(engine.read_bytes())["containers"]["2"*64]["State"]["Running"]


def test_busy_sync_lock_never_sends_term_or_changes_config(tmp_path, monkeypatch):
    run, engine, config, output, _, claims = fixture(tmp_path, monkeypatch)
    wrapper = tmp_path / "bin/flock"
    wrapper.write_text('#!/bin/sh\ncase " $* " in *" -w "*) exit 1;; esac\nexec /usr/bin/flock "$@"\n')
    wrapper.chmod(0o755)
    before = config.read_bytes()
    assert run("install").returncode != 0
    state = json.loads(engine.read_bytes())
    assert state["events"] == ["load"] and state["containers"]["1"*64]["State"]["Running"]
    assert config.read_bytes() == before and (output / "sync-state.json").read_bytes() == claims


def test_partial_config_write_never_replaces_original_and_rolls_back(tmp_path, monkeypatch):
    run, engine, config, output, _, claims = fixture(tmp_path, monkeypatch)
    wrapper = tmp_path / "bin/cat"
    wrapper.write_text('#!/bin/sh\ncase "$*" in *config-enabled.toml*) printf partial; exit 1;; esac\nexec /usr/bin/cat "$@"\n')
    wrapper.chmod(0o755)
    before = config.read_bytes()
    assert run("install").returncode != 0
    state = json.loads(engine.read_bytes())
    assert len(state["containers"]) == 1 and state["containers"]["1"*64]["State"]["Running"]
    assert config.read_bytes() == before and (output / "sync-state.json").read_bytes() == claims

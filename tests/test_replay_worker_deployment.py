"""Docker isolation policy and the inode-stable HTML adapter, without Docker I/O."""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_is_explicit_nonroot_offline_readonly_resource_bounded():
    value = yaml.safe_load((ROOT / "replay-worker/compose.yaml").read_text())
    service = value["services"]["replay-worker"]
    assert service["profiles"] == ["operator-approved"]
    assert service["user"] == "10001:10001" and service["read_only"] is True
    assert service["network_mode"] == "none" and service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert service["cpus"] == .5 and service["cpu_shares"] == 64
    assert service["mem_limit"] == service["memswap_limit"] == "768m"
    assert service["pids_limit"] == 128 and service["restart"] == "no"
    assert service["pull_policy"] == "never"
    assert set(v["target"] for v in service["volumes"]) == {"/archive", "/replays"}
    assert service["volumes"][0]["read_only"] is True
    assert all(v["bind"]["create_host_path"] is False for v in service["volumes"])
    assert "environment" not in service and "env_file" not in service
    assert not any(k in service for k in ("devices", "privileged", "ports", "pid"))


@pytest.mark.parametrize("event", ["socket.__new__", "socket.connect", "socket.bind",
                                  "socket.getaddrinfo", "subprocess.Popen", "os.system",
                                  "os.exec", "os.posix_spawn"])
def test_native_audit_denies_network_processes_and_device_dispatch(event):
    from eos_pv_helper.replay_worker_job import deny_external_actions

    with pytest.raises(PermissionError, match="offline_replay_external_action_denied"):
        deny_external_actions(event, ())


def test_host_launcher_rejects_mutable_image_and_records_exact_isolation(tmp_path):
    source, work, tools = [tmp_path / name for name in ("source", "work", "bin")]
    for path in (source, work, tools):
        path.mkdir()
    capture = tmp_path / "args.json"
    fake = tools / "docker"
    fake.write_text("#!/usr/bin/env python3\nimport json,sys\n"
                    "from pathlib import Path\nPath("+repr(str(capture))+
                    ").write_text(json.dumps(sys.argv[1:]))\n")
    fake.chmod(0o755)
    env = {**os.environ, "PATH": str(tools)+os.pathsep+os.environ["PATH"]}
    script = ROOT / "scripts/unraid-native-replay-worker.sh"
    for image in ("latest", "eos-replay-worker:latest", "$(touch bad)"):
        assert subprocess.run(["bash", script, image, source, work], env=env,
                              capture_output=True).returncode == 2
    assert not capture.exists()
    result = subprocess.run(["bash", script, "sha256:"+"a"*64, source, work],
                            env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    args = json.loads(capture.read_text())
    assert args[:4] == ["--host", "unix:///var/run/docker.sock", "run", "--rm"]
    assert args[args.index("--network")+1] == "none"
    assert "--read-only" in args and "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges" in args
    assert "--memory=768m" in args and "--cpus=0.50" in args
    mounts = [args[i+1] for i, arg in enumerate(args) if arg == "--mount"]
    assert len(mounts) == 2 and mounts[0].endswith("target=/archive,readonly")
    assert all("sock" not in m for m in mounts)
    assert "--privileged" not in args and "-e" not in args


def test_adapter_snapshot_is_stable_if_catalog_replaced_during_publisher(tmp_path):
    tools, work, publish, replays = [tmp_path / name for name in (
        "tools", "work", "publish", "replays")]
    for path in (tools, work, publish, replays):
        path.mkdir()
    catalog = replays / "catalog.json"
    catalog.write_text('{"generation":1}')
    replacement = replays / "replacement.json"
    replacement.write_text('{"generation":2}')
    publisher = tools / "unraid-dashboard-publish.sh"
    publisher.write_text("#!/bin/bash\nset -euo pipefail\n"
                         "[ \"$4\" = --replays ]\n"
                         "mv -- "+repr(str(replacement))+" "+repr(str(catalog))+"\n"
                         "cat -- \"$5\" > \"$3/index.html\"\n")
    result = subprocess.run(["bash", ROOT / "scripts/unraid-dashboard-replay-catalog.sh",
                             tools, work, publish, replays], capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((publish / "index.html").read_text()) == {"generation": 1}
    assert json.loads(catalog.read_text()) == {"generation": 2}
    assert not list(work.iterdir())


@pytest.mark.parametrize("case", ["symlink", "oversized"])
def test_adapter_unsafe_catalog_never_invokes_publisher(tmp_path, case):
    paths = [tmp_path / name for name in ("tools", "work", "publish", "replays")]
    for path in paths:
        path.mkdir()
    catalog = paths[3] / "catalog.json"
    if case == "symlink":
        other = tmp_path / "untrusted"
        other.write_text("{}")
        catalog.symlink_to(other)
    else:
        with catalog.open("wb") as handle:
            handle.truncate(32_000_001)
    result = subprocess.run(["bash", ROOT / "scripts/unraid-dashboard-replay-catalog.sh", *paths],
                            capture_output=True)
    assert result.returncode == 2 and not list(paths[2].iterdir())

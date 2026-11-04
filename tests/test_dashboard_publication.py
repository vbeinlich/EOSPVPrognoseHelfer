"""Actual pinned reader through fake Docker; publication never touches EMS input."""

import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from test_dashboard import fingerprint, packet
from test_dashboard_wrapper import harness as harness

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def publication(harness, tmp_path):
    source, work, env, _ = harness
    tools = tmp_path / "tools"
    tools.mkdir()
    shutil.copyfile(tmp_path / "dashboard.pyz", tools / "ems-dashboard-final.pyz")
    shutil.copyfile(ROOT / "scripts/unraid-ems-dashboard.sh", tools / "unraid-ems-dashboard.sh")
    public = tmp_path / "publish"
    public.mkdir(mode=0o755)

    def run(case="", destination=public, extra=()):
        before = fingerprint(source)
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/unraid-dashboard-publish.sh"),
             str(tools), str(work), str(destination), *extra],
            capture_output=True, env={**env, "CASE": case}, timeout=30,
        )
        assert fingerprint(source) == before
        return result

    return source, work, tools, public, env, run


def test_publication_atomic_failure_retention_recovery(publication):
    source, work, tools, public, env, run = publication
    assert run().returncode == 0
    valid = packet(public / "index.html")
    assert len(valid["plans"]) == 3
    assert (public / "index.html").stat().st_mode & 0o777 == 0o644
    assert (work / "index.html").stat().st_mode & 0o077 == 0
    for case in ("truncated", "transport"):
        assert run(case).returncode == 1
        assert packet(public / "index.html")["plans"] == valid["plans"]
        assert 'id="transport-error" class=' in (public / "index.html").read_text()
    assert run().returncode == 0
    assert 'id="transport-error" hidden' in (public / "index.html").read_text()
    (source / "sync-state.json").write_text('{"broken":')
    assert run().returncode == 2
    assert packet(public / "index.html")["plans"] == valid["plans"]
    assert packet(public / "index.html")["update_error"] is True
    # Corrupted tool bytes must not be executed or replace the retained plans.
    with (tools / "ems-dashboard-final.pyz").open("ab") as stream:
        stream.write(b"corrupt")
    assert run().returncode == 1
    assert packet(public / "index.html")["plans"] == valid["plans"]
    assert sorted(p.name for p in public.iterdir()) == ["index.html"]
    assert not list(work.glob(".seed-*"))
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert all(command[0] in ("ps", "inspect", "exec") for command in commands)


def test_initial_invalid_source_does_not_publish_false_success(publication):
    source, _, _, public, _, run = publication
    (source / "sync-state.json").write_text("{")
    assert run().returncode == 2
    report = packet(public / "index.html")
    assert report["update_error"] is True
    assert report["plans"] == []


def test_public_cache_seeds_private_recovery(publication):
    source, work, _, public, _, run = publication
    assert run().returncode == 0
    plans = packet(public / "index.html")["plans"]
    (work / "index.html").unlink()
    (source / "sync-state.json").write_text("{")
    assert run().returncode == 2
    assert packet(public / "index.html")["plans"] == plans


def test_synthetic_http_event_uses_real_private_to_public_reader(publication):
    source, work, tools, public, env, run = publication
    assert run().returncode == 0
    previous = len(packet(public / "index.html")["plans"])
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/dashboard_event.py"), "--source", str(source),
         "--destination", str(work), "--publication-tools", str(tools),
         "--publication-destination", str(public)],
        capture_output=True, env=env, timeout=40,
    )
    assert result.returncode == 0, result.stderr
    assert len(packet(public / "index.html")["plans"]) == previous + 1
    assert (public / "index.html").stat().st_mode & 0o777 == 0o644
    assert (work / "index.html").stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("relative", ["", "nested"])
def test_never_publish_into_originals_or_parent(publication, relative):
    source, _, _, _, _, run = publication
    dest = source / relative
    dest.mkdir(exist_ok=True)
    assert run(destination=dest).returncode == 2
    assert not (dest / "index.html").exists()
    assert not (source / ".publish.lock").exists()
    assert run(destination=source.parent).returncode == 2


def test_reject_symlink_and_serialize_exports(publication, tmp_path):
    _, work, _, public, env, run = publication
    other = tmp_path / "protected"
    other.write_text("untouched")
    (public / "index.html").symlink_to(other)
    assert run().returncode == 2
    assert other.read_text() == "untouched"
    (public / "index.html").unlink()
    with (work / ".publish.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run().returncode == 0
    commands = Path(env["COMMAND_LOG"]).read_text()
    assert '"exec"' not in commands
    assert not (public / "index.html").exists()


def test_pinned_unchanged_pr25_reader_and_hardened_server_contract():
    manifest = json.loads((ROOT / "docs/DASHBOARD_CODE_HASHES.json").read_text())
    publisher = (ROOT / "scripts/unraid-dashboard-publish.sh").read_text()
    assert manifest["dashboard_bundle_sha256"] in publisher
    wrapper = (ROOT / "scripts/unraid-ems-dashboard.sh").read_bytes()
    assert hashlib.sha256(wrapper).hexdigest() == manifest["unraid_wrapper_sha256"]
    assert manifest["unraid_wrapper_sha256"] in publisher
    compose = yaml.safe_load((ROOT / "deploy/dashboard/compose.yaml").read_text())
    server = compose["services"]["dashboard"]
    assert server["image"].startswith("nginxinc/nginx-unprivileged@sha256:")
    assert server["user"] == "101:101" and server["read_only"] is True
    assert server["cap_drop"] == ["ALL"]
    assert server["security_opt"] == ["no-new-privileges:true"]
    assert all(mount["read_only"] and not mount["bind"]["create_host_path"]
               for mount in server["volumes"])
    assert {m["target"] for m in server["volumes"]} == {"/srv/dashboard", "/etc/nginx/nginx.conf"}
    assert compose["networks"]["static_only"]["driver_opts"]["com.docker.network.bridge.enable_icc"] == "false"
    assert "DASHBOARD_LAN_IP:?" in server["ports"][0]
    assert not ({"devices", "privileged", "network_mode", "pid", "ipc"} & server.keys())
    config = (ROOT / "deploy/dashboard/nginx.conf").read_text()
    assert "location / { return 404; }" in config and "disable_symlinks on;" in config
    assert "proxy_pass" not in config and "autoindex on" not in config


@pytest.fixture
def preflight(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    commands = {
        "ip": '#!/bin/bash\nprintf "%s\\n" "2: br0 inet ${ADDRESS:-192.168.0.186}/24 brd 192.168.0.255 scope global br0"\n',
        "ss": '#!/bin/bash\nprintf "%s\\n" "${LISTENERS:-}"\n',
        "docker": '#!/bin/bash\n[ "$1" = --host ] && [ "$2" = unix:///var/run/docker.sock ] || exit 1\nshift 2\ncase "$1" in ps) printf "%s\\n" aabbccddeeff;; inspect) printf "%s\\n" "${DOCKER_PORT:-}";; *) exit 99;; esac\n',
    }
    for name, text in commands.items():
        file = binary / name
        file.write_text(text)
        file.chmod(0o755)

    def run(ip="192.168.0.186", **variables):
        return subprocess.run(
            ["bash", str(ROOT / "scripts/unraid-dashboard-preflight.sh"), ip],
            env={**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"], **variables},
            capture_output=True, timeout=10,
        )

    return run


def test_preflight_checks_address_tcp_and_docker_publication(preflight):
    assert preflight().returncode == 0
    assert preflight(ADDRESS="192.168.0.187").returncode == 1
    for address in ("0.0.0.0", "192.168.0.186", "[::]", "127.0.0.1"):
        assert preflight(LISTENERS=f"LISTEN 0 128 {address}:8505 0.0.0.0:*").returncode == 1
    assert preflight(DOCKER_PORT="8505").returncode == 1
    assert preflight(DOCKER_PORT="8504").returncode == 0


@pytest.mark.parametrize("ip", ["0.0.0.0", "127.0.0.1", "8.8.8.8", "::", "192.168.0.999", "192.168.00.186", "172.32.0.1", "1;echo oops"])
def test_preflight_rejects_unintended_bind_addresses(preflight, ip):
    assert preflight(ip).returncode == 2

"""Full Unraid wrapper with fake Docker transport and the real isolated stdin reader."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
from build_ems_dashboard import build
from dashboard_fixture import make
from test_dashboard import fingerprint, packet

ROOT = Path(__file__).resolve().parents[1]
DOCKER = r"""#!/usr/bin/env python3
import json,os,subprocess,sys
args=sys.argv[1:]
assert args[:2]==['--host','unix:///var/run/docker.sock']
args=args[2:]
with open(os.environ['COMMAND_LOG'],'a') as log:log.write(json.dumps(args)+'\n')
case=os.environ.get('CASE','')
if args[0]=='ps':
    if case!='none':print('aabbccddeeff')
    if case=='two':print('112233445566')
elif args[0]=='inspect':
    if '.Mounts' in args[2]:print(os.environ['SOURCE'])
    else:print('true ghcr.io/vbeinlich/eospvprognosehelfer@sha256:'+'d'*64)
elif args[:8]==['exec','-i','aabbccddeeff','python','-I','-S','-B','-c']:
    if case=='transport':raise SystemExit(1)
    if case=='truncated':
        sys.stdout.write('<!doctype html>')
        raise SystemExit(0)
    bootstrap=args[8].replace("'/output'",repr(os.environ['SOURCE']))
    sys.exit(subprocess.run([sys.executable,'-I','-S','-B','-c',bootstrap,*args[9:]],stdin=sys.stdin.buffer).returncode)
else:raise SystemExit('Forbidden Docker command')
"""


@pytest.fixture
def harness(tmp_path):
    source = make(tmp_path / "source")
    dest = tmp_path / "dashboard"
    dest.mkdir()
    code = tmp_path / "dashboard.pyz"
    code.write_bytes(build())
    sha = hashlib.sha256(code.read_bytes()).hexdigest()
    binary = tmp_path / "bin"
    binary.mkdir()
    fake = binary / "docker"
    fake.write_text(DOCKER)
    fake.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "SOURCE": str(source),
        "COMMAND_LOG": str(tmp_path / "commands.jsonl"),
    }

    def run(case="", destination=dest, digest=sha, extra=()):
        before = fingerprint(source)
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts/unraid-ems-dashboard.sh"),
                str(code),
                digest,
                str(destination),
                *extra,
            ],
            capture_output=True,
            env={**env, "CASE": case},
            timeout=30,
        )
        assert fingerprint(source) == before
        return result

    return source, dest, env, run


def test_unraid_wrapper_atomic_export_recovery_and_transport_error(harness):
    source, dest, env, run = harness
    assert run().returncode == 0
    valid = packet(dest / "index.html")
    assert len(valid["plans"]) == 3
    assert run("truncated").returncode == 1
    assert packet(dest / "index.html")["plans"] == valid["plans"]
    assert run("transport").returncode == 1
    assert 'id="transport-error" class=' in (dest / "index.html").read_text()
    assert packet(dest / "index.html")["plans"] == valid["plans"]
    assert run().returncode == 0
    assert 'id="transport-error" hidden' in (dest / "index.html").read_text()
    (source / "sync-state.json").write_text('{"broken":')
    assert run().returncode == 2
    assert packet(dest / "index.html")["plans"] == valid["plans"]
    assert packet(dest / "index.html")["update_error"] is True
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert all(c[0] in ("ps", "inspect", "exec") for c in commands)
    assert not list(dest.glob(".ems-*"))


@pytest.mark.parametrize("case", ["none", "two"])
def test_missing_or_multiple_helpers_never_started(harness, case):
    _, dest, _, run = harness
    assert run(case).returncode != 0
    assert not (dest / "index.html").exists()


def test_source_output_is_never_a_dashboard_destination(harness):
    source, _, _, run = harness
    assert run(destination=source).returncode == 2
    assert not (source / ".refresh.lock").exists()


def test_wrong_hash_never_calls_docker(harness):
    _, dest, env, run = harness
    assert run(digest="f" * 64).returncode != 0
    assert not Path(env["COMMAND_LOG"]).exists()
    assert not (dest / "index.html").exists()

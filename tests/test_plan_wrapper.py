"""Fake Docker transport, actual verified bundle and real read-only Python reader."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import build_plan_inspector
import pytest
from test_plan_inspector import fingerprint, fixture

ROOT = Path(__file__).resolve().parents[1]
DOCKER = r'''#!/usr/bin/env python3
import json,os,subprocess,sys
args=sys.argv[1:]
assert args[:2]==['--host','unix:///var/run/docker.sock']
args=args[2:]
with open(os.environ['COMMAND_LOG'],'a') as log:log.write(json.dumps(args)+'\n')
mode=os.environ.get('CASE','')
if args[0]=='ps':
    assert args==['ps','--quiet','--no-trunc']
    if mode!='no-helper':print('aabbccddeeff')
    if mode=='two':print('112233445566')
elif args[0]=='inspect':
    if '.Mounts' in args[2]:print('/wrong' if mode=='mount' else '/output')
    elif args[2]=='{{.State.Running}} {{.Config.Image}}':
        if mode=='inspect-error':raise SystemExit('Synthetic inspect error')
        print(('false' if mode=='stopped' else 'true')+' '+('ghcr.io/other/application:latest' if mode=='wrong' else 'ghcr.io/vbeinlich/eospvprognosehelfer@sha256:'+'d'*64))
    else:raise SystemExit('Forbidden inspect dump')
elif args[:8]==['exec','-i','aabbccddeeff','python','-I','-S','-B','-c']:
    bootstrap=args[8].replace("'/output'",repr(os.environ['SOURCE']))
    sys.exit(subprocess.run([sys.executable,'-I','-S','-B','-c',bootstrap,*args[9:]],stdin=sys.stdin.buffer).returncode)
else:raise SystemExit('Forbidden Docker command')
'''


@pytest.fixture
def harness(tmp_path):
    source = tmp_path / "source"
    fixture(source)
    code = tmp_path / "inspector.pyz"
    code.write_bytes(build_plan_inspector.build())
    digest = hashlib.sha256(code.read_bytes()).hexdigest()
    binary = tmp_path / "bin"
    binary.mkdir()
    fake = binary / "docker"
    fake.write_text(DOCKER)
    fake.chmod(0o755)
    env = {**os.environ, "PATH": str(binary)+os.pathsep+os.environ["PATH"],
           "SOURCE": str(source), "COMMAND_LOG": str(tmp_path / "commands.jsonl")}
    def run(case="", sha=digest, extra=()):
        before = fingerprint(source)
        result = subprocess.run(["bash", str(ROOT / "scripts/unraid-plan-inspector.sh"), str(code), sha, *extra],
            capture_output=True, env={**env, "CASE": case}, timeout=20)
        assert before == fingerprint(source)
        return result
    return source, code, digest, env, run


def test_real_bundle_bootstrap_emits_html_and_sanitized_json(harness):
    _, _, _, env, run = harness
    html = run()
    assert html.returncode == 0, html.stderr.decode()
    assert html.stdout.startswith(b"<!doctype html>")
    assert b"DO-NOT-READ" not in html.stdout
    result = run(extra=("--json",))
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["plans"][0]["source_slots"] == 24
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert all(c[0] in {"ps", "inspect", "exec"} for c in commands)


@pytest.mark.parametrize("case", ["no-helper", "two", "mount", "wrong", "stopped", "inspect-error"])
def test_transport_errors_fail_closed_without_report_or_changes(harness, case):
    result = harness[-1](case)
    assert result.returncode != 0 and not result.stdout


def test_wrong_bundle_hash_and_write_flags_never_access_docker(harness):
    _, _, _, env, run = harness
    assert run(sha="f"*64).returncode != 0
    assert run(extra=("--write-eos",)).returncode == 2
    assert not Path(env["COMMAND_LOG"]).exists()


def test_busy_shared_lock_and_corrupt_bundle_have_no_partial_report(harness):
    import fcntl
    source, code, _, _, run = harness
    with (source / "sync.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = run()
        assert result.returncode != 0 and not result.stdout
    code.write_bytes(b"corrupt")
    result = run(sha=hashlib.sha256(b"corrupt").hexdigest())
    assert result.returncode != 0 and not result.stdout

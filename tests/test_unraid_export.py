"""Synthetic local process tests: fake Docker/curl, real pinned exporter and lock.

No Docker socket, network, production files or optimizer is used by these tests.
"""

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
import test_doctor as fixtures

ROOT = Path(__file__).resolve().parents[1]

FAKE_DOCKER = r'''#!/usr/bin/env python3
import io,json,os,subprocess,sys,zipfile
from pathlib import Path
args=sys.argv[1:]
assert args[:2]==['--host','unix:///var/run/docker.sock']
args=args[2:]
with open(os.environ['COMMAND_LOG'],'a') as log: log.write(json.dumps(args)+'\n')
mode=os.environ.get('CASE','')
if args[0]=='ps':
    if mode!='no-helper': print('aabbccddeeff ghcr.io/vbeinlich/eospvprognosehelfer@sha256:'+'d'*64)
    if mode=='two-helpers': print('112233445566 ghcr.io/vbeinlich/eospvprognosehelfer:pr-3')
elif args[0]=='inspect':
    template=args[2]
    if '.Mounts' in template: print('/output\n'+('/wrong' if mode=='mount' else '/app/config.toml'))
    elif template=='{{.Image}}': print('sha256:'+'c'*64)
    else:
        assert '.Config.Env' not in template and '{{json .}}' not in template
        print(json.dumps({'container_id':'aabbccddeeff','name':'/synthetic-helper','configured_image':'ghcr.io/vbeinlich/eospvprognosehelfer:synthetic','image_id':'sha256:'+'c'*64}))
elif args[:2]==['image','inspect']:
    print(json.dumps({'source':'https://github.com/vbeinlich/EOSPVPrognoseHelfer','revision':'b'*40,'version':'synthetic'}))
elif args[:4]==['exec','-i','aabbccddeeff','python']:
    if args[4]=='-':
        assert args[5:]==['--source','/output','--config','/app/config.toml']
        result=subprocess.run([sys.executable,'-','--source',os.environ['ARTIFACTS'],'--config',os.environ['TEST_CONFIG']],input=sys.stdin.buffer.read(),capture_output=True)
        raw=result.stdout
        if mode=='zip-corrupt': raw=b'not a ZIP'
        if mode=='hash' and raw:
            with zipfile.ZipFile(io.BytesIO(raw)) as z: files={n:z.read(n) for n in z.namelist()}
            files['prices.json']+=b' '
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                for n,b in files.items(): z.writestr(n,b)
            raw=out.getvalue()
        sys.stdout.buffer.write(raw);sys.stderr.buffer.write(result.stderr);sys.exit(result.returncode)
    assert args[4]=='-c'
    sys.exit(subprocess.run([sys.executable,'-c',args[5]],stdin=sys.stdin.buffer).returncode)
else: raise SystemExit('Forbidden Docker command')
'''


@pytest.fixture
def harness(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    artifacts = fixtures.artifacts.__wrapped__(source)
    fixtures.inspect(artifacts)
    config = tmp_path / "private.toml"
    config.write_text('timezone="Europe/Berlin"\nprivate_key="CONFIG-CANARY-NEVER-EXPORT"\n'
                      '[soc]\nmax_age_seconds=60\nmax_abs_power_w=9000\n'
                      '[evcc]\ntoken_file="/run/secrets/DO-NOT-READ"\n')
    (source / "token").write_text("FILE-CANARY-NEVER-EXPORT")
    bin_dir, exports = tmp_path / "bin", tmp_path / "exports"
    bin_dir.mkdir()
    exports.mkdir()
    programs = {"docker": FAKE_DOCKER,
        "mktemp": "#!/usr/bin/env python3\nimport os,tempfile\nprint(tempfile.mkdtemp(dir=os.environ['EXPORTS']))\n",
        "curl": "#!/usr/bin/env python3\nimport os,sys\nfrom pathlib import Path\np=Path(sys.argv[sys.argv.index('--output')+1]);p.write_bytes(b'bad' if os.environ.get('CASE')=='script-hash' else Path(os.environ['EXPORTER']).read_bytes())\n"}
    for name, program in programs.items():
        path = bin_dir / name
        path.write_text(program)
        path.chmod(0o755)
    env = {**os.environ, "PATH": str(bin_dir)+os.pathsep+os.environ["PATH"],
        "ARTIFACTS": str(source), "TEST_CONFIG": str(config), "EXPORTS": str(exports),
        "EXPORTER": str(ROOT / "scripts/doctor_snapshot.py"), "COMMAND_LOG": str(tmp_path / "commands.jsonl")}

    def run(case=""):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir() if p.is_file()}
        result = subprocess.run(["bash", str(ROOT / "scripts/unraid-doctor-export.sh")],
                                env={**env, "CASE": case}, capture_output=True, timeout=30)
        assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir() if p.is_file()}
        assert b"CONFIG-CANARY" not in result.stdout+result.stderr
        assert b"FILE-CANARY" not in result.stdout+result.stderr
        return result

    return source, exports, env, run


def test_export_has_exact_files_no_config_secrets_and_preserves_raw_artifacts(harness):
    source, exports, env, run = harness
    result = run()
    assert result.returncode == 0, result.stderr.decode()
    path = next(exports.glob("*/doctor-snapshot.zip"))
    assert path.stat().st_mode & 0o077 == 0
    assert b"not Doctor acceptance" in result.stdout
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("snapshot.json"))
        assert len(archive.namelist()) == 5
        assert manifest["validation_constraints"]["max_age_seconds"] == 60
        for name, digest in manifest["files"].items():
            raw = archive.read(name)
            assert raw == (source / name).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == digest
        assert b"CANARY" not in b"".join(archive.read(n) for n in archive.namelist())
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert all(c[0] in {"ps", "inspect", "image", "exec"} for c in commands)


@pytest.mark.parametrize("case", ["no-helper", "two-helpers", "mount", "script-hash", "zip-corrupt", "hash"])
def test_wrapper_errors_never_publish_a_final_archive(harness, case):
    _, exports, _, run = harness
    assert run(case).returncode != 0
    assert not list(exports.glob("*/doctor-snapshot.zip"))
    assert all(p.stat().st_size == 0 for p in exports.glob("*/*.partial"))


@pytest.mark.parametrize("key,value", [("token", "synthetic-secret"), ("private_key", "synthetic-key"),
    ("configuration", {"url": "private-config"}), ("unexpected", "ghp_"+"x"*36)])
def test_unexpected_sensitive_artifact_content_is_blocked_without_redacting_originals(harness, key, value):
    source, exports, _, run = harness
    report = source / "sync-report.json"
    payload = json.loads(report.read_text())
    payload[key] = value
    report.write_text(json.dumps(payload))
    assert run().returncode != 0
    assert not list(exports.glob("*/doctor-snapshot.zip"))


def test_writer_lock_causes_immediate_failure_without_stopping_writer(harness):
    import fcntl
    source, exports, _, run = harness
    with (source / "sync.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        assert run().returncode != 0
    assert not list(exports.glob("*/doctor-snapshot.zip"))


@pytest.mark.parametrize("failure", ["missing", "symlink"])
def test_missing_or_symlinked_artifact_never_becomes_an_export(harness, failure):
    source, exports, env, run = harness
    path = source / "prices.json"
    path.unlink()
    if failure == "symlink":
        path.symlink_to(env["TEST_CONFIG"])
    assert run().returncode != 0
    assert not list(exports.glob("*/doctor-snapshot.zip"))

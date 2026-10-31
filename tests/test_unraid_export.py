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
from test_historical_doctor import complete_artifacts, second_claim, snapshot, waiting

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
    if mode=='display-bare' and args==['ps','--format','{{.ID}} {{.Image}}']:
        print('aabbccddeeff ghcr.io/vbeinlich/eospvprognosehelfer');sys.exit(0)
    assert args==['ps','--quiet','--no-trunc']
    if mode!='no-helper': print('aabbccddeeff')
    if mode in ('two-helpers','other-containers'): print('112233445566')
elif args[0]=='inspect':
    template=args[2]
    if template=='{{.State.Running}} {{.Config.Image}}':
        if mode=='inspect-error': raise SystemExit('Synthetic inspect failure')
        image=os.environ.get('CONFIG_IMAGE','ghcr.io/vbeinlich/eospvprognosehelfer@sha256:'+'d'*64)
        if mode=='other-containers' and args[3]=='112233445566': image='ghcr.io/other/application:latest'
        print(('false' if mode=='stopped' else 'true')+' '+image)
    elif '.Mounts' in template: print('/output\n'+('/wrong' if mode=='mount' else '/app/config.toml'))
    elif template=='{{.Image}}': print('sha256:'+'c'*64)
    else:
        assert '.Config.Env' not in template and '{{json .}}' not in template
        print(json.dumps({'container_id':'aabbccddeeff','name':'/synthetic-helper','configured_image':'ghcr.io/vbeinlich/eospvprognosehelfer:synthetic','image_id':'sha256:'+'c'*64}))
elif args[:2]==['image','inspect']:
    print(json.dumps({'source':'https://github.com/vbeinlich/EOSPVPrognoseHelfer','revision':'b'*40,'version':'synthetic'}))
elif args[:4]==['exec','-i','aabbccddeeff','python']:
    assert args[4:8]==['-I','-S','-B','-c']
    extra=[os.environ['ARTIFACTS'] if a=='/output' else os.environ['TEST_CONFIG'] if a=='/app/config.toml' else a for a in args[9:]]
    result=subprocess.run([sys.executable,'-I','-S','-B','-c',args[8],*extra],input=sys.stdin.buffer.read(),capture_output=True)
    raw=result.stdout
    if '--source' in extra and '--emit' in extra and result.returncode==0:
        if mode=='zip-corrupt': raw=b'not a ZIP'
        if mode=='hash':
            with zipfile.ZipFile(io.BytesIO(raw)) as z: files={n:z.read(n) for n in z.namelist()}
            files['prices.json']+=b' '
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                for n,b in files.items(): z.writestr(n,b)
            raw=out.getvalue()
    sys.stdout.buffer.write(raw);sys.stderr.buffer.write(result.stderr);sys.exit(result.returncode)
else: raise SystemExit('Forbidden Docker command')
'''


@pytest.fixture
def harness(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    complete_artifacts(source)
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

    def run(case="", arguments=("--export",), image=None):
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in source.iterdir() if p.is_file()}
        options = {**env, "CASE": case}
        if image is not None:
            options["CONFIG_IMAGE"] = image
        script = ROOT / "scripts/unraid-doctor-export.sh"
        if case == "script-hash":
            script = tmp_path / "bad-wrapper.sh"
            script.write_text((ROOT / "scripts/unraid-doctor-export.sh").read_text().replace(
                'No network, extraction, timestamp repair', 'No network, extraction, timestamp edit'))
        result = subprocess.run(["bash", str(script), *arguments],
                                env=options, capture_output=True, timeout=30)
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
        assert len(archive.namelist()) == 8
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


def test_preflight_reads_under_lock_without_export_download_or_private_output(harness):
    _, exports, env, run = harness
    result = run(arguments=("--check-only",))
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout) == {"preflight": "passed", "read_only": True,
        "shared_lock_verified": True, "artifact_count": 7, "export_created": False,
        "doctor_acceptance": False}
    assert list(exports.iterdir()) == []
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert all(command[0] in {"ps", "inspect", "exec"} for command in commands)


def test_default_mode_is_read_only_preflight(harness):
    _, exports, _, run = harness
    result = run(arguments=())
    assert result.returncode == 0
    assert json.loads(result.stdout)["export_created"] is False
    assert list(exports.iterdir()) == []


def test_unraid_bare_ps_display_uses_full_inspected_digest_reference(harness):
    _, exports, env, run = harness
    image = 'ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7'
    assert run("display-bare", arguments=("--check-only",), image=image).returncode == 0
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert commands[0] == ["ps", "--quiet", "--no-trunc"]
    assert ["inspect", "--format", "{{.State.Running}} {{.Config.Image}}", "aabbccddeeff"] in commands
    assert list(exports.iterdir()) == []


@pytest.mark.parametrize("suffix", ["", ":latest", ":pr-3", "@sha256:"+"a"*64,
    ":v0.1.0@sha256:"+"b"*64])
def test_exact_configured_repository_accepts_valid_tag_and_digest_forms(harness, suffix):
    _, exports, _, run = harness
    result = run(arguments=("--check-only",), image="ghcr.io/vbeinlich/eospvprognosehelfer"+suffix)
    assert result.returncode == 0, result.stderr.decode()
    assert list(exports.iterdir()) == []


@pytest.mark.parametrize("image", ["ghcr.io/other/eospvprognosehelfer:latest",
    "docker.io/vbeinlich/eospvprognosehelfer:latest",
    "ghcr.io/vbeinlich/eospvprognosehelfer-other:latest",
    "ghcr.io/vbeinlich/eospvprognosehelfer@sha256:abc",
    "ghcr.io/vbeinlich/eospvprognosehelfer@sha256:"+"g"*64,
    "ghcr.io/vbeinlich/eospvprognosehelfer@sha512:"+"a"*64,
    "ghcr.io/vbeinlich/eospvprognosehelfer:"])
def test_unrelated_or_malformed_configured_images_are_rejected(harness, image):
    _, exports, env, run = harness
    assert run(arguments=("--check-only",), image=image).returncode != 0
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert not any(command[0] == "exec" for command in commands)
    assert list(exports.iterdir()) == []


@pytest.mark.parametrize("case", ["two-helpers", "stopped", "inspect-error"])
def test_only_one_still_running_inspected_helper_is_accepted(harness, case):
    _, exports, _, run = harness
    assert run(case, arguments=("--check-only",)).returncode != 0
    assert list(exports.iterdir()) == []


def test_other_running_application_is_ignored_without_exec(harness):
    _, exports, env, run = harness
    assert run("other-containers", arguments=("--check-only",)).returncode == 0
    commands = [json.loads(line) for line in Path(env["COMMAND_LOG"]).read_text().splitlines()]
    assert not any(command[0] == "exec" and command[2] == "112233445566" for command in commands)
    assert list(exports.iterdir()) == []


@pytest.mark.parametrize("failure", ["writer", "missing-file", "wrong-claim"])
def test_preflight_fails_closed_without_creating_any_export(harness, failure):
    import fcntl
    from contextlib import nullcontext
    source, exports, _, run = harness
    if failure == "missing-file":
        (source / "prices.json").unlink()
    elif failure == "wrong-claim":
        path = source / "sync-state.json"
        value = json.loads(path.read_text())
        next(iter(value["events"].values()))["status"] = "uncertain"
        path.write_text(json.dumps(value))
    context = (source / "sync.lock").open("rb") if failure == "writer" else nullcontext()
    with context as handle:
        if handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
        assert run(arguments=("--check-only",)).returncode != 0
    assert list(exports.iterdir()) == []


def test_unknown_cli_option_never_touches_docker_or_creates_output(harness):
    _, exports, env, run = harness
    assert run(arguments=("--force",)).returncode == 2
    assert not Path(env["COMMAND_LOG"]).exists()
    assert list(exports.iterdir()) == []


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


def historical_case(harness):
    source, exports, _, _ = harness
    files = {p.name: json.loads(p.read_bytes()) for p in source.glob("*.json")}
    artifacts = source, {"output": {"directory": str(source)}}, files
    raw = snapshot(artifacts)
    path = exports.parent / "existing-private-snapshot.zip"
    path.write_bytes(raw)
    waiting(artifacts)
    second_claim(artifacts)
    return path, raw, files["sync-report.json"]["event"]["version"]


def test_waiting_publication_without_history_explains_missing_evidence(harness):
    source, exports, _, run = harness
    historical_case(harness)
    for mode in ("--check-only", "--export"):
        result = run(arguments=(mode,))
        assert result.returncode != 0
        assert b"2 succeeded claim(s) do not prove saved prices/SoC/PV" in result.stderr
    assert list(exports.iterdir()) == []
    assert json.loads((source / "sync-report.json").read_bytes())["event"] == {"status": "waiting-publication"}


def test_historical_preflight_and_export_keep_original_archive_and_capture_time(harness):
    source, exports, _, run = harness
    path, raw, version = historical_case(harness)
    for name in ("prices.json", "soc.json", "forecast.json", "report.json"):
        (source / name).write_text('{"current_data_is_not_history":true}')
    options = ("--historical-snapshot", str(path), "--event-version", version)
    assert run(arguments=("--check-only", *options)).returncode == 0
    assert not list(exports.iterdir())
    result = run(arguments=("--export", *options))
    assert result.returncode == 0, result.stderr.decode()
    assert next(exports.glob("*/doctor-snapshot.zip")).read_bytes() == raw
    assert path.read_bytes() == raw


@pytest.mark.parametrize("failure", ["missing", "symlink", "legacy", "wrong-version", "inconsistent"])
def test_historical_wrapper_fails_closed_without_partial_export(harness, failure):
    source, exports, _, run = harness
    path, raw, version = historical_case(harness)
    if failure == "missing":
        path.unlink()
    elif failure == "symlink":
        path.unlink()
        path.symlink_to(source / "sync-report.json")
    elif failure == "legacy":
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("snapshot.json", '{"schema_version":1}')
    elif failure == "wrong-version":
        version = "f"*64
    else:
        with zipfile.ZipFile(path) as archive:
            contents = {n: archive.read(n) for n in archive.namelist()}
        contents["prices.json"] += b" "
        with zipfile.ZipFile(path, "w") as archive:
            for name, payload in contents.items():
                archive.writestr(name, payload)
    result = run(arguments=("--export", "--historical-snapshot", str(path), "--event-version", version))
    assert result.returncode != 0
    assert not list(exports.iterdir())

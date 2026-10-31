"""Consume ACTUAL auto-writer synthetic archives in existing immutable images.

No helper/project source mounts, no image pull/build, production access or optimizer.
Run tests/make_evidence_fixture.py first; its HTTP dispatch is completely mocked.
"""

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def smoke(image, context, fixture, expect_no_doctor=False):
    def docker(*args, **kwargs):
        return subprocess.run(["docker", "--context", context, *args], timeout=180,
                              capture_output=True, **kwargs)
    host = json.loads(docker("context", "inspect", context, check=True).stdout)[0]["Endpoints"]["docker"]["Host"]
    if not host.startswith(("unix://", "npipe://")):
        raise ValueError("Explicit local development Docker context required")
    info = json.loads(docker("image", "inspect", image, check=True).stdout)[0]
    image_id = info["Id"]
    engine = (ROOT / "src/eos_pv_helper/historical.py").read_bytes().rstrip(b"\n")
    secure = ["run", "--rm", "--pull=never", "--network", "none", "--read-only", "--cap-drop=ALL",
              "--security-opt=no-new-privileges", "--user", "10001:10001", "--entrypoint", "python"]
    probe = """import importlib.util,json
from pathlib import Path
s=importlib.util.find_spec('eos_pv_helper')
p=Path(s.origin).parent if s else None
print(json.dumps({'doctor_present':bool(p and (p/'doctor.py').is_file())}))
"""
    runtime = json.loads(docker(*secure, image_id, "-B", "-c", probe, check=True).stdout)
    if expect_no_doctor:
        assert runtime["doctor_present"] is False
    fixture = Path(fixture).resolve()
    original = (fixture / "snapshot.zip").read_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        manifest = json.loads(archive.read("snapshot.json"))
        assert manifest["producer"]["contract"] == "eos-pv-helper/automatic-evidence-v1"
        version = manifest["event_version"]
    before = {str(p.relative_to(fixture)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
              for p in fixture.rglob("*") if p.is_file()}
    mounts = []
    for name, target in (("snapshot.zip", "/snapshot.zip"), ("limits.toml", "/limits.toml"),
                         ("inspection", "/output")):
        mounts += ["--mount", f"type=bind,source={fixture / name},target={target},readonly"]
    def run(*args):
        result = docker(*secure, "-i", *mounts, image_id, "-I", "-S", "-B", "-", *args, input=engine)
        assert b"Traceback" not in result.stderr and b"ModuleNotFoundError" not in result.stderr, result.stderr.decode()
        return result
    isolated = docker(*secure, image_id, "-I", "-S", "-B", "-c",
        "import importlib.util; assert importlib.util.find_spec('eos_pv_helper') is None", check=True)
    assert isolated.returncode == 0
    base = ("--source", "/output", "--config", "/limits.toml")
    waiting = run(*base, "--check-only")
    assert waiting.returncode == 1 and b"waiting-publication" in waiting.stderr
    historical = run(*base, "--snapshot", "/snapshot.zip", "--event-version", version, "--check-only")
    assert historical.returncode == 0, historical.stderr.decode()
    assert json.loads(historical.stdout)["export_created"] is False
    offline = run("--snapshot", "/snapshot.zip")
    assert offline.returncode == 0, offline.stderr.decode()
    result = json.loads(offline.stdout)
    assert result["accepted"] and all(result["checks"].values())
    assert len(result["artifact_sha256"]) == 7 and result["current_freshness_verified"] is False
    assert result["captured_at_utc"] == manifest["captured_at_utc"]
    emitted = run(*base, "--snapshot", "/snapshot.zip", "--emit")
    assert emitted.returncode == 0 and emitted.stdout == original
    wrong = run(*base, "--snapshot", "/snapshot.zip", "--event-version", "f"*64)
    assert wrong.returncode == 1 and b"version differs" in wrong.stderr
    after = {str(p.relative_to(fixture)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
             for p in fixture.rglob("*") if p.is_file()}
    assert before == after
    return {"passed": True, "scenarios": 5, "synthetic_only": True, "image_id": image_id,
            "repo_digests": info.get("RepoDigests", []), "runtime": runtime,
            "source_revision": info["Config"].get("Labels", {}).get("org.opencontainers.image.revision"),
            "engine_sha256": hashlib.sha256(engine).hexdigest(), "archive_sha256": hashlib.sha256(original).hexdigest(),
            "project_source_mounted": False, "helper_importable": False, "network": "none", "read_only": True,
            "production_access": False, "approved": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--docker-context", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--expect-no-doctor", action="store_true")
    args = parser.parse_args()
    print(json.dumps(smoke(args.image, args.docker_context, args.fixture, args.expect_no_doctor), indent=2))

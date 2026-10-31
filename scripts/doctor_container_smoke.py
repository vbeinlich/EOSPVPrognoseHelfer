"""Real-container regression, with synthetic inputs and no app source mounts.

Only existing images on an explicitly local development Docker context are used.
No pull, build, production connection, optimization, persistent container or export.
"""

import argparse
import hashlib
import io
import json
import re
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fixtures():
    """Independent synthetic fixture; no installed helper imports on the host."""
    now = datetime(2026, 10, 29, 13, 5, tzinfo=UTC)
    start = now.replace(hour=0, minute=0)
    prices = {"data": {(start+timedelta(minutes=15*i)).isoformat():
                       {"elecprice_marketprice_wh": .0003} for i in range(192)}}
    # Fixed synthetic winter day; host Windows needs no timezone data package.
    delivery = datetime(2026, 10, 30).date()
    left = datetime(2026, 10, 29, 23, tzinfo=UTC)
    rows = [[(left+timedelta(minutes=15*i)).isoformat(), .0003] for i in range(96)]
    version = hashlib.sha256(json.dumps([str(delivery), rows], separators=(",", ":")).encode()).hexdigest()
    claim = {"version": version, "delivery_day": str(delivery), "delivery_intervals": 96,
             "claimed_at_utc": now.isoformat(), "start_utc": now.replace(minute=0).isoformat(),
             "status": "succeeded", "control_hours": 24, "interval_seconds": 3600, "effective_tail_hours": 10}
    soc = {"usable": True, "source": "evcc", "freshness_verified": True,
           "source_timestamp": now.isoformat(), "percent": 55, "factor": .55,
           "timestamp_kind": "successful_uncached_device_read_lower_bound",
           "freshness_evidence": {"contract": "evcc-0.318.1/e3dc-rscp/uncached-getters",
               "live_soc_percent": 55, "live_power_w": -354, "read_started_at_utc": now.isoformat(),
               "read_completed_at_utc": now.isoformat()}}
    pv = {"checked_at_utc": now.isoformat(), "count": 288, "import_verified": True,
          "start_utc": start.isoformat(), "end_exclusive_utc": (start+timedelta(hours=72)).isoformat(),
          "source_fetched_at_utc": now.isoformat(), "source_max_age_seconds": 3600}
    values = {"sync-report.json": {"checked_at_utc": now.isoformat(), "mode": "write", "errors": {},
              "event": claim, "pv": pv, "soc": {**soc, "import_verified": True},
              "prices": {"count": 192, "unit": "EUR/Wh", "import_verified": True,
                         "control_coverage": {"control_complete": True, "required_control_hours": 24}}},
              "sync-state.json": {"pv_import_verified": True, "events": {version: claim}},
              "prices.json": prices, "soc.json": soc, "report.json": pv,
              "forecast.json": {"data": {(start+timedelta(minutes=15*i)).isoformat():
                                {"pvforecast_ac_power": 0 if i % 96 < 24 else 1000} for i in range(288)}},
              "solution-"+version+".json": {"interval_seconds": 3600, "start_solution_datetime": claim["start_utc"],
                  "ac_charge": [0]*24, "dc_charge": [1]*24, "discharge_allowed": [1]*24,
                  "result": {"total_costs": -1.25}}}
    files = {name: json.dumps(value).encode() for name, value in values.items()}
    manifest = {"schema_version": 2, "event_version": version, "captured_at_utc": now.isoformat(),
                "timezone": "Europe/Berlin", "configured_constraints_read": True,
                "validation_constraints": {"max_age_seconds": 300, "max_abs_power_w": 20000},
                "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    return version, files, manifest


def archive(manifest, files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("snapshot.json", json.dumps(manifest))
        for name, raw in files.items():
            z.writestr(name, raw)
    return stream.getvalue()


def smoke(image, context, *, expect_no_doctor=False):
    def docker(*args, **kwargs):
        return subprocess.run(["docker", "--context", context, *args], capture_output=True,
                              timeout=180, **kwargs)

    endpoint = json.loads(docker("context", "inspect", context, check=True).stdout)[0]["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith(("unix://", "npipe://")):
        raise ValueError("Only a local development Docker endpoint is allowed")
    info = json.loads(docker("image", "inspect", image, check=True).stdout)[0]
    # Execute the inspected immutable image ID; never trust a mutable tag later.
    image_id = info["Id"]
    wrapper = (ROOT / "scripts/unraid-doctor-export.sh").read_text(encoding="utf-8")
    engine = wrapper.split("historical_engine=$(cat <<'PY_ENGINE'\n", 1)[1].split("\nPY_ENGINE\n", 1)[0]
    engine_sha = hashlib.sha256(engine.encode()).hexdigest()
    if re.search(r"^engine_sha256=([0-9a-f]{64})$", wrapper, re.M)[1] != engine_sha:
        raise ValueError("Embedded engine SHA256 mismatch")
    if engine != (ROOT / "src/eos_pv_helper/historical.py").read_text(encoding="utf-8").rstrip("\n"):
        raise ValueError("Embedded engine differs from reviewed source")
    secure = ["run", "--rm", "--pull=never", "--network", "none", "--read-only", "--cap-drop=ALL",
              "--security-opt=no-new-privileges", "--user", "10001:10001", "--entrypoint", "python"]
    probe = """import importlib.util,json,sys
from pathlib import Path
p=importlib.util.find_spec('eos_pv_helper')
root=Path(p.origin).parent if p is not None else None
print(json.dumps({'python':sys.version.split()[0],
    'modules':{name: bool(root and (root/(name+'.py')).is_file()) for name in ('doctor','inputs','normalize','historical')}}))
"""
    runtime = json.loads(docker(*secure, image_id, "-B", "-c", probe, check=True).stdout)
    if expect_no_doctor and runtime["modules"]["doctor"]:
        raise ValueError("Regression image unexpectedly contains doctor.py")
    isolated = docker(*secure, image_id, "-I", "-S", "-B", "-c",
        "import importlib.util,json; print(json.dumps({'helper_visible':importlib.util.find_spec('eos_pv_helper') is not None}))", check=True)
    if json.loads(isolated.stdout)["helper_visible"]:
        raise ValueError("Isolated interpreter can still import installed helper")

    with tempfile.TemporaryDirectory(prefix="doctor-container-synthetic-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        source = root / "output"
        source.mkdir(mode=0o755)
        version, files, manifest = fixtures()
        original = archive(manifest, files)
        (root / "snapshot.zip").write_bytes(original)
        bad = dict(files)
        bad["prices.json"] += b" "
        (root / "invalid.zip").write_bytes(archive(manifest, bad))
        state = json.loads(files["sync-state.json"])
        state["events"]["a"*64] = {**state["events"][version], "version": "a"*64}
        for name, raw in files.items():
            (source / name).write_bytes(raw)
        (source / "sync-state.json").write_text(json.dumps(state))
        (source / "sync-report.json").write_text(json.dumps({"event": {"status": "waiting-publication"}, "errors": {}}))
        (source / ("solution-"+"a"*64+".json")).write_bytes(files["solution-"+version+".json"])
        # Current inputs must not be silently used for the historical success.
        for name in ("prices.json", "soc.json", "forecast.json", "report.json"):
            (source / name).write_text('{"newer_live_data":true}')
        (source / "sync.lock").touch()
        (root / "config.toml").write_text('timezone="Europe/Berlin"\n[soc]\nmax_age_seconds=300\n')
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        def fingerprint():
            return {str(p.relative_to(root)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in root.rglob("*") if p.is_file()}
        before = fingerprint()
        mounts = []
        for host, target in ((source, "/output"), (root / "config.toml", "/config.toml"),
                             (root / "snapshot.zip", "/snapshot.zip"), (root / "invalid.zip", "/invalid.zip")):
            mounts += ["--mount", f"type=bind,source={host},target={target},readonly"]
        def run(*args):
            result = docker(*secure, *mounts, image_id, "-I", "-S", "-B", "-c", engine, *args)
            if b"Traceback" in result.stderr or b"ModuleNotFoundError" in result.stderr:
                raise ValueError("Engine emitted a traceback in the real container")
            return result
        def blocked(result, reason):
            assert result.returncode == 1, result.stderr.decode()
            value = json.loads(result.stderr)
            assert value["accepted"] is False and value["read_only"] is True
            assert reason in value["reason"], value
            assert not result.stdout
        base = ("--source", "/output", "--config", "/config.toml")
        blocked(run(*base, "--check-only"), "waiting-publication")
        result = run(*base, "--snapshot", "/snapshot.zip", "--event-version", version, "--check-only")
        assert result.returncode == 0, result.stderr.decode()
        assert json.loads(result.stdout)["export_created"] is False
        result = run("--snapshot", "/snapshot.zip")
        assert result.returncode == 0, result.stderr.decode()
        accepted = json.loads(result.stdout)
        assert accepted["accepted"] and all(accepted["checks"].values())
        assert accepted["current_freshness_verified"] is False and len(accepted["artifact_sha256"]) == 7
        assert accepted["captured_at_utc"] == manifest["captured_at_utc"]
        blocked(run("--snapshot", "/invalid.zip"), "SHA256 mismatch")
        blocked(run(*base, "--snapshot", "/snapshot.zip", "--event-version", "f"*64), "version differs")
        result = run(*base, "--snapshot", "/snapshot.zip", "--emit")
        assert result.returncode == 0 and result.stdout == original, result.stderr.decode()
        assert before == fingerprint(), "Synthetic input bytes/mtime changed"
    return {"passed": True, "synthetic_only": True, "scenarios": 6, "image_id": image_id,
            "repo_digests": info.get("RepoDigests", []), "engine_sha256": engine_sha,
            "runtime": runtime, "helper_visible_in_isolated_interpreter": False,
            "source_revision": info["Config"].get("Labels", {}).get("org.opencontainers.image.revision"),
            "network": "none", "read_only": True, "uid": 10001, "project_source_mounted": False,
            "production_access": False, "approved": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Existing local image, never pulled by this tool")
    parser.add_argument("--docker-context", required=True, help="Explicit local development context")
    parser.add_argument("--expect-no-doctor", action="store_true")
    args = parser.parse_args()
    print(json.dumps(smoke(args.image, args.docker_context, expect_no_doctor=args.expect_no_doctor), indent=2))

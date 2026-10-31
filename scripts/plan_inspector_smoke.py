"""Real old-container compatibility with code-only bundle, synthetic read-only input."""

import argparse
import hashlib
import json
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from build_plan_inspector import build

ROOT = Path(__file__).resolve().parents[1]


def smoke(image, context, html=None):
    def docker(*args, **kwargs):
        return subprocess.run(["docker", "--context", context, *args], capture_output=True, timeout=180, **kwargs)
    host = json.loads(docker("context", "inspect", context, check=True).stdout)[0]["Endpoints"]["docker"]["Host"]
    if not host.startswith(("unix://", "npipe://")):
        raise ValueError("Local development Docker context required")
    info = json.loads(docker("image", "inspect", image, check=True).stdout)[0]
    image_id = info["Id"]
    wrapper = (ROOT / "scripts/unraid-plan-inspector.sh").read_text(encoding="utf-8")
    bootstrap = wrapper.split("bootstrap=$(cat <<'PY_BOOT'\n", 1)[1].split("\nPY_BOOT\n", 1)[0]
    bundle = build()
    sha = hashlib.sha256(bundle).hexdigest()
    with tempfile.TemporaryDirectory(prefix="plan-inspector-synthetic-") as folder:
        root = Path(folder)
        root.chmod(0o755)
        events = {}
        for index, (seconds, count) in enumerate(((3600, 24), (900, 96))):
            version = ("a" if index == 0 else "b")*64
            start = datetime(2026, 10, 29+index, 13, tzinfo=UTC)
            events[version] = {"version": version, "status": "succeeded", "start_utc": start.isoformat(),
                "claimed_at_utc": (start+timedelta(minutes=5)).isoformat(), "control_hours": 24,
                "effective_tail_hours": 10, "interval_seconds": seconds}
            solution = {"start_solution_datetime": start.isoformat(), "interval_seconds": seconds,
                        "controls_start_at_now": True, "ac_charge": [0, .5]*(count//2),
                        "dc_charge": [1]*count, "discharge_allowed": [1, 0]*(count//2),
                        "result": {"total_costs": 2.6875, "battery_soc_per_hour": [55]*count},
                        "parameters": {"password": "PRIVATE-CANARY-192.168.0.99"}}
            (root / ("solution-"+version+".json")).write_text(json.dumps(solution))
        (root / "sync-state.json").write_text(json.dumps({"events": events}))
        (root / "sync-report.json").write_text('{"event":{"status":"waiting-publication"}}')
        (root / "prices.json").write_text('{"private_live_canary":"DO-NOT-READ"}')
        (root / "sync.lock").touch()
        for file in root.iterdir():
            file.chmod(0o444)
        before = {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.iterdir()}
        secure = ["run", "--rm", "--pull=never", "--network", "none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--user", "10001:10001", "--entrypoint", "python"]
        isolated = docker(*secure, image_id, "-I", "-S", "-B", "-c",
            "import importlib.util; assert importlib.util.find_spec('eos_pv_helper') is None", check=True)
        assert isolated.returncode == 0
        def run(fmt):
            return docker(*secure, "-i", "--mount", f"type=bind,source={root},target=/output,readonly",
                          image_id, "-I", "-S", "-B", "-c", bootstrap, sha, fmt, "", input=bundle)
        result = run("json")
        assert result.returncode == 0, result.stderr.decode()
        report = json.loads(result.stdout)
        assert report["latest_sync_status"] == "waiting-publication"
        assert len(report["plans"]) == 2
        assert sorted(p["source_slots"] for p in report["plans"]) == [24, 96]
        assert all(sum(len(r["quarters"]) for r in p["rows"]) == 96 for p in report["plans"])
        result = run("html")
        assert result.returncode == 0 and result.stdout.startswith(b"<!doctype html>"), result.stderr.decode()
        assert b"PRIVATE-CANARY" not in result.stdout and b"DO-NOT-READ" not in result.stdout
        after = {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.iterdir()}
        assert before == after
        if html:
            with Path(html).open("xb") as handle:
                handle.write(result.stdout)  # New synthetic UI-test artifact only, never source files.
    return {"passed": True, "synthetic_only": True, "image_id": image_id, "source_files_unchanged": True,
            "project_source_mounted": False, "installed_helper_importable": False, "network": "none",
            "read_only": True, "uid": 10001, "bundle_sha256": sha, "phase": 1}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--docker-context", required=True)
    parser.add_argument("--html", help="NEW synthetic test report outside the input fixture")
    args = parser.parse_args()
    print(json.dumps(smoke(args.image, args.docker_context, args.html), indent=2))

"""Old-image acceptance: code-only stdin bundle, UID 10001, no network/source writes."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from build_ems_dashboard import build
from dashboard_fixture import make

ROOT = Path(__file__).resolve().parents[1]


def smoke(image, context, html=None):
    def docker(*args, **kwargs):
        return subprocess.run(
            ["docker", "--context", context, *args], capture_output=True, timeout=120, **kwargs
        )

    host = json.loads(docker("context", "inspect", context, check=True).stdout)[0]["Endpoints"][
        "docker"
    ]["Host"]
    if not host.startswith(("unix://", "npipe://")):
        raise ValueError("Local test Docker context required")
    image_id = json.loads(docker("image", "inspect", image, check=True).stdout)[0]["Id"]
    wrapper = (ROOT / "scripts/unraid-ems-dashboard.sh").read_text()
    bootstrap = wrapper.split("bootstrap=$(cat <<'PY_BOOT'\n", 1)[1].split("\nPY_BOOT\n", 1)[0]
    bundle = build()
    sha = hashlib.sha256(bundle).hexdigest()
    with tempfile.TemporaryDirectory(prefix="ems-dashboard-synthetic-") as temporary:
        root = make(Path(temporary) / "source")
        Path(temporary).chmod(0o755)
        root.chmod(0o755)
        for p in root.iterdir():
            p.chmod(0o444)

        def fingerprint():
            return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}

        secure = [
            "run",
            "--rm",
            "--pull=never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user",
            "10001:10001",
            "--mount",
            f"type=bind,source={root},target=/output,readonly",
            "--entrypoint",
            "python",
        ]
        before = fingerprint()
        run = docker(
            *secure,
            "-i",
            image_id,
            "-I",
            "-S",
            "-B",
            "-c",
            bootstrap,
            sha,
            str(len(bundle)),
            input=bundle,
        )
        assert run.returncode == 0, run.stderr.decode()
        assert before == fingerprint()
        rendered = run.stdout
        assert rendered.startswith(b"<!doctype html>")
        report = json.loads(
            re.search(
                rb'<script id="dashboard-data" type="application/json">(.*?)</script>',
                rendered,
                re.S,
            )[1]
        )
        assert len(report["plans"]) == 3 and not report["update_error"]
        assert report["plans"][0]["rows"][0]["flow"]["pv_wh"] is None
        assert b"PRIVATE-CANARY" not in rendered and b"NEVER-READ" not in rendered
        damaged = root / "sync-state.json"
        damaged.chmod(0o600)
        damaged.write_text('{"truncated":')
        damaged.chmod(0o444)
        before = fingerprint()
        run = docker(
            *secure,
            "-i",
            image_id,
            "-I",
            "-S",
            "-B",
            "-c",
            bootstrap,
            sha,
            str(len(bundle)),
            input=bundle + rendered,
        )
        assert run.returncode == 2, run.stderr.decode()
        fallback = json.loads(
            re.search(
                rb'<script id="dashboard-data" type="application/json">(.*?)</script>',
                run.stdout,
                re.S,
            )[1]
        )
        assert fallback["plans"] == report["plans"] and fallback["update_error"] is True
        assert before == fingerprint()
        if html:
            with Path(html).open("xb") as output:
                output.write(rendered)
    return {
        "passed": True,
        "image_id": image_id,
        "uid": 10001,
        "read_only": True,
        "network": "none",
        "source_files_unchanged": True,
        "last_good_recovery": True,
        "project_source_mounted": False,
        "bundle_sha256": sha,
        "synthetic_only": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--docker-context", required=True)
    parser.add_argument("--html")
    args = parser.parse_args()
    print(json.dumps(smoke(args.image, args.docker_context, args.html), indent=2))

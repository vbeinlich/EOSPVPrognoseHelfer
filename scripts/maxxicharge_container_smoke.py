"""Local Docker smoke: no access to Unraid, Docker sockets in containers or devices."""

import argparse
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, timeout=60).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="ems-maxxicharge-simulator:poc-local")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-parent", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--phase2", action="store_true")
    args = parser.parse_args()
    context = json.loads(docker("context", "inspect"))[0]
    for endpoint in (context["Endpoints"]["docker"]["Host"], os.environ.get("DOCKER_HOST", "")):
        if endpoint and not endpoint.startswith(("npipe:///", "unix:///")):
            raise ValueError("Smoke test requires a local Docker daemon")
    source = Path(args.input_dir).resolve(strict=True)
    output = Path(args.output_parent).resolve(strict=True)
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Input and output must be disjoint")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()
              if p.is_file()}
    name = "ems-maxxicharge-poc-smoke-" + uuid.uuid4().hex[:12]
    identifier = docker("create", "--name", name, "--network", "none", "--read-only",
        "--user", "10001:10001", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "384m", "--cpus", "0.5", "--pids-limit", "32",
        "--mount", f"type=bind,source={source},target=/input,readonly",
        "--mount", f"type=bind,source={output},target=/output",
        args.image, "--input", "/input/input.json", "--config", "/input/config.json",
        "--output", "/output/run", *(["--phase2"] if args.phase2 else []))
    try:
        state = json.loads(docker("inspect", identifier))[0]
        assert state["Name"] == "/" + name
        assert state["HostConfig"]["NetworkMode"] == "none"
        assert state["HostConfig"]["ReadonlyRootfs"] is True
        assert state["Config"]["User"] == "10001:10001"
        assert state["HostConfig"]["CapDrop"] == ["ALL"]
        assert "no-new-privileges" in " ".join(state["HostConfig"]["SecurityOpt"])
        assert state["HostConfig"]["RestartPolicy"]["Name"] == "no"
        assert not state["HostConfig"].get("Devices")
        assert not state["HostConfig"].get("PortBindings")
        assert len(state["Mounts"]) == 2
        assert next(m for m in state["Mounts"] if m["Destination"] == "/input")["RW"] is False
        docker("start", "--attach", identifier)
        state = json.loads(docker("inspect", identifier))[0]
        assert state["State"]["ExitCode"] == 0 and not state["State"]["OOMKilled"]
        assert json.loads((output / "run/manifest.json").read_bytes())["complete"] is True
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()
                 if p.is_file()}
        assert before == after
        result = {"passed": True, "network": "none", "uid": "10001:10001",
                  "read_only_root": True, "inputs_unchanged": True,
                  "image_id": state["Image"], "source_mount_read_only": True,
                  "started_at": state["State"]["StartedAt"],
                  "finished_at": state["State"]["FinishedAt"],
                  "devices_commanded": False, "production_changed": False}
        result["comparison_phase"] = 2 if args.phase2 else 1
        with Path(args.report).open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        print(json.dumps(result))
    finally:
        # Remove only the exact container this script created; no volume deletion.
        docker("rm", "--force", identifier)


if __name__ == "__main__":
    main()

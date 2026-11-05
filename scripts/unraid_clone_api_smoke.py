"""Actual local Docker CREATE metadata compatibility. NEVER starts a helper or worker."""

import argparse
import http.client
import importlib.util
import io
import json
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).parents[1]


def check(image):
    docker = ["docker", "--context", "desktop-linux"]

    def command(*args):
        return subprocess.check_output([*docker, *args], text=True).strip()

    assert command("context", "inspect", "desktop-linux", "--format", '{{.Endpoints.docker.Host}}') == "npipe:////./pipe/dockerDesktopLinuxEngine"
    spec = importlib.util.spec_from_file_location("prepare", ROOT / "deploy/unraid-test/prepare.py")
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    prefix = "ems-install-api-review-"+uuid.uuid4().hex
    names = [prefix+"-old", prefix+"-clone"]
    try:
        command("create", "--name", names[0], "--pull=never", "--network", "none", "--read-only",
                "--user", "10001:10001", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--cpus=.25", "--memory=512m", "--pids-limit=128", "--volume", "/output",
                image, "sync", "--config", "/app/config.toml", "--refresh-source", "--write-eos")
        original = json.loads(command("inspect", names[0]))[0]
        payload = prepare.clone_payload(original, image)
        body = json.dumps(payload).encode()
        version = command("version", "--format", '{{.Server.APIVersion}}')
        request = (f"POST /v{version}/containers/create?name={names[1]} HTTP/1.1\r\n"
                   f"Host: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                   "Connection: close\r\n\r\n").encode()+body
        # Short-lived LOCAL API client only, no helper entrypoint. Neither of the
        # reviewed helper/worker runtimes receives this socket. No start endpoint.
        client = "import socket,sys;s=socket.socket(socket.AF_UNIX);s.settimeout(20);s.connect('/var/run/docker.sock');s.sendall(sys.stdin.buffer.read());\nwhile True:\n b=s.recv(65536)\n if not b:break\n sys.stdout.buffer.write(b)"
        raw = subprocess.run([*docker, "run", "--rm", "-i", "--network", "none", "--read-only",
            "--user", "0:0", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--mount", "type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock,readonly",
            "--entrypoint", "python", image, "-c", client], input=request,
            capture_output=True, timeout=40, check=True).stdout

        class BufferSocket:
            def makefile(self, *args, **kwargs):
                return io.BytesIO(raw)

        response = http.client.HTTPResponse(BufferSocket())
        response.begin()
        response_raw = response.read()
        result = json.loads(response_raw)
        assert response.status == 201, result
        clone = json.loads(command("inspect", names[1]))[0]
        assert not original["State"]["Running"] and not clone["State"]["Running"]
        for key in ("Entrypoint", "Cmd", "Env", "User", "WorkingDir", "Healthcheck"):
            assert original["Config"].get(key) == clone["Config"].get(key)
        for key in ("Memory", "NanoCpus", "PidsLimit", "NetworkMode", "ReadonlyRootfs", "CapDrop", "SecurityOpt"):
            assert original["HostConfig"].get(key) == clone["HostConfig"].get(key)
        def mounts(info):
            # An unstarted named volume may still report its name in Source.
            return [(m["Type"], m.get("Name") if m["Type"] == "volume" else m["Source"],
                     m["Destination"], m["RW"]) for m in info["Mounts"]]
        assert mounts(original) == mounts(clone), (mounts(original), mounts(clone), payload["HostConfig"]["Binds"])
        return {"test": "local-docker-create-api", "api_version": version, "passed": True,
                "helper_processes_started": 0, "optimizer_searches": 0, "device_actions": 0,
                "anonymous_output_volume_preserved": True, "command_environment_limits_preserved": True}
    finally:
        for name in reversed(names):
            subprocess.run([*docker, "rm", "--volumes", name], capture_output=True, timeout=30)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = check(args.image)
    args.report.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report))

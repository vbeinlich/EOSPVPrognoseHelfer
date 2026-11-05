"""Local Docker acceptance with disposable synthetic volumes, never production data."""

import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path


def check(image, fixture_image, context):
    docker = ["docker", "--context", context]

    def command(*args, timeout=180):
        result = subprocess.run([*docker, *args], capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            # This command only ever handles synthetic fixtures and reviewed images.
            raise RuntimeError("Local replay acceptance command failed: " + result.stderr[-2000:])
        return result.stdout.strip()

    endpoint = command("context", "inspect", context, "--format", '{{.Endpoints.docker.Host}}')
    if endpoint not in ("unix:///var/run/docker.sock", "npipe:////./pipe/dockerDesktopLinuxEngine",
                        "npipe:////./pipe/docker_engine"):
        raise ValueError("Only a local Docker endpoint is permitted")
    image = command("image", "inspect", image, "--format", "{{.Id}}")
    fixture_image = command("image", "inspect", fixture_image, "--format", "{{.Id}}")
    prefix = "ems-replay-review-" + uuid.uuid4().hex
    source, workspace, container = prefix+"-source", prefix+"-workspace", prefix+"-job"
    created_volumes = []
    created_container = False
    try:
        for name in (source, workspace):
            command("volume", "create", "--label", "eos.synthetic-replay-review=true", name)
            created_volumes.append(name)
        initializer = r'''
import hashlib,json,os
from datetime import timedelta
from pathlib import Path
from replay_worker_fixture import create
from eos_pv_helper.replay_worker import Worker
source,workspace=Path('/archive'),Path('/replays')
os.chown(source,0,0); os.chown(workspace,0,0)
source.chmod(0o700); workspace.chmod(0o700)
version,claimed,_=create(source)
worker=Worker(source,workspace,now=lambda:claimed-timedelta(seconds=1))
worker.tick()
before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.rglob('*') if p.is_file()}
(workspace/'original-fingerprints.json').write_text(json.dumps(before))
for root in (source,workspace):
    children=sorted(root.rglob('*'),key=lambda p:len(p.parts),reverse=True)
    for p in children: os.chown(p,10001,10001)
    os.chown(root,10001,10001)
print(json.dumps({'synthetic_only':True,'initialized':True}))
'''
        command("run", "--rm", "--network", "none", "--read-only", "--user", "0:0",
                "--cap-drop=ALL", "--cap-add=CHOWN", "--security-opt=no-new-privileges",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777",
                "--mount", f"type=volume,source={source},target=/archive",
                "--mount", f"type=volume,source={workspace},target=/replays",
                "--entrypoint", "python", fixture_image, "-c", initializer)
        command("create", "--name", container, "--network", "none", "--read-only",
                "--user", "10001:10001", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--cpus=0.50", "--cpu-shares=64", "--memory=768m", "--memory-swap=768m",
                "--pids-limit=128", "--ulimit", "core=0:0", "--ulimit", "nofile=1024:1024",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777",
                "--mount", f"type=volume,source={source},target=/archive,readonly",
                "--mount", f"type=volume,source={workspace},target=/replays",
                image, "--timeout", "90", "--cpu-seconds", "30", "--address-space-mb", "3072")
        created_container = True
        start = time.monotonic()
        first = command("start", "--attach", container)
        elapsed = time.monotonic()-start
        info = json.loads(command("inspect", container))[0]
        host = info["HostConfig"]
        assert info["State"]["ExitCode"] == 0 and not info["State"]["OOMKilled"], first
        assert host["NetworkMode"] == "none" and host["ReadonlyRootfs"]
        assert info["Config"]["User"] == "10001:10001"
        assert host["CapDrop"] == ["ALL"] and host["SecurityOpt"] == ["no-new-privileges"]
        assert host["Memory"] == 768*1024**2 and host["MemorySwap"] == host["Memory"]
        assert host["NanoCpus"] == 500_000_000 and host["PidsLimit"] == 128
        assert not host["Privileged"] and not host["Devices"]
        assert len(info["Mounts"]) == 2
        assert {m["Destination"]: m["RW"] for m in info["Mounts"]} == {
            "/archive": False, "/replays": True}
        verify = r'''
import hashlib,json
from pathlib import Path
from eos_pv_helper.replay_worker_catalog import Catalog
root=Path('/replays'); source=Path('/archive')
before=json.loads((root/'original-fingerprints.json').read_bytes())
after={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
       for p in source.rglob('*') if p.is_file()}
assert before==after
catalog=Catalog(root).load(); assert len(catalog['plans'])==1
receipt=json.loads(next((root/'receipts').glob('*.json')).read_bytes())
status=json.loads((root/'state/status.json').read_bytes())
assert [j['status'] for j in status['jobs'].values()]==['verified']
print(json.dumps({'synthetic_only':True,'originals_unchanged':True,'plans':1,
                 'receipt_hash':receipt['sha256'],'metrics':receipt['metrics']}))
'''

        def inspected():
            return json.loads(command("run", "--rm", "--network", "none", "--read-only",
                "--user", "10001:10001", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777",
                "--mount", f"type=volume,source={source},target=/archive,readonly",
                "--mount", f"type=volume,source={workspace},target=/replays,readonly",
                "--entrypoint", "python", fixture_image, "-c", verify))

        before = inspected()
        command("start", "--attach", container)
        after = inspected()
        assert before == after
        return {"contract": "eos-pv-helper/replay-worker-resource-review-v1",
                "synthetic_only": True, "runtime_isolation_verified": True,
                "originals_unchanged": True, "second_run_did_not_replay": True,
                "native_revision": "8a8cd43a1915668927eda5504b7de039c2e762b4",
                "controls": 24, "container_wall_seconds": round(elapsed, 3),
                "cpu_quota": .5, "ram_limit_mib": 768, "pids_limit": 128,
                "native_metrics": before["metrics"]}
    finally:
        if created_container:
            command("rm", "--force", container)
        for name in created_volumes:
            assert name.startswith(prefix)
            command("volume", "rm", name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--fixture-image", required=True)
    parser.add_argument("--docker-context", default="default")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = check(args.image, args.fixture_image, args.docker_context)
    raw = json.dumps(report, indent=2)+"\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            handle.write(raw)
    print(raw)

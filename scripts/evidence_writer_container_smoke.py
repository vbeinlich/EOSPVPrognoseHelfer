"""Two separately packaged local images, real sync writer/native replay, synthetic data only."""

import argparse
import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(helper_image, worker_image, context):
    docker = ["docker", "--context", context]

    def command(*args, timeout=180):
        result = subprocess.run([*docker, *args], capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            raise RuntimeError("Synthetic writer review failed: " + result.stderr[-3000:])
        return result.stdout.strip()

    endpoint = command("context", "inspect", context, "--format", '{{.Endpoints.docker.Host}}')
    if endpoint not in ("unix:///var/run/docker.sock", "npipe:////./pipe/dockerDesktopLinuxEngine",
                        "npipe:////./pipe/docker_engine"):
        raise ValueError("Only a local Docker endpoint is permitted")
    helper_image = command("image", "inspect", helper_image, "--format", "{{.Id}}")
    worker_image = command("image", "inspect", worker_image, "--format", "{{.Id}}")
    prefix = "ems-evidence-review-"+uuid.uuid4().hex
    common = ["--rm", "--name", prefix+"-run", "--network", "none", "--read-only", "--user", "10001:10001",
              "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=.5", "--memory=768m",
              "--memory-swap=768m", "--pids-limit=128",
              "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777"]
    source, workspace = prefix+"-source", prefix+"-replays"
    created = []
    try:
        for name in (source, workspace):
            command("volume", "create", "--label", "eos.synthetic-writer-review=true", name)
            created.append(name)
        initializer = r'''
import os
from pathlib import Path
from eos_pv_helper.storage import atomic_json
for name in ('/output','/replays'):
    p=Path(name); os.chown(p,0,0); p.chmod(0o700)
atomic_json(Path('/output/sync-state.json'),{'events':{}})
Path('/output/sync.lock').touch(mode=0o600)
for name in ('/output','/replays'):
    p=Path(name)
    for child in p.iterdir(): os.chown(child,10001,10001)
    os.chown(p,10001,10001)
'''
        # Only brand new random synthetic volumes, no operator paths or original data.
        command("run", "--rm", "--name", prefix+"-init", "--network", "none", "--read-only", "--user", "0:0",
                "--cap-drop=ALL", "--cap-add=CHOWN",
                "--security-opt=no-new-privileges", "--mount", f"type=volume,source={source},target=/output",
                "--mount", f"type=volume,source={workspace},target=/replays,volume-nocopy",
                "--entrypoint", "python", helper_image, "-c", initializer)

        def worker():
            result = command("run", *common,
                "--mount", f"type=volume,source={source},target=/archive,readonly",
                "--mount", f"type=volume,source={workspace},target=/replays,volume-nocopy",
                worker_image, "--settle-seconds", "1")
            return json.loads(result.splitlines()[-1])

        assert worker()["counts"]["verified"] == 0  # Activate before the normal synthetic event.
        driver = r'''
import hashlib,json,os,resource,runpy,time
from datetime import UTC,datetime
from pathlib import Path
from eos_pv_helper import sync,evidence
ns=runpy.run_path('/review/synthetic.py'); ns['deny_real_actions']()
os.environ['DRY_RUN']='false'  # Test process only: there is no real HTTP transport.
event=ns['SyntheticEvent']('/output','/review/template.json',now=datetime.now(UTC))
original=sync.archive_success; elapsed=[]
def measured(*args,**kwargs):
    start=time.monotonic()
    try: return original(*args,**kwargs)
    finally: elapsed.append(time.monotonic()-start)
sync.archive_success=measured
start=time.monotonic(); report=event.tick(); wall=time.monotonic()-start
assert report['errors']=={} and report['evidence']['status']=='archived',report.get('evidence')
assert event.tick()['evidence']['status']=='archived' and event.model_calls==1
installed=json.loads(Path('/usr/share/eos-pv-helper/licenses/evidence-writer.json').read_bytes())
import importlib.util
for name,digest in installed['source_sha256'].items():
    path=Path(importlib.util.find_spec('eos_pv_helper.'+name).origin)
    assert '/site-packages/' in str(path) and hashlib.sha256(path.read_bytes()).hexdigest()==digest
print(json.dumps({'synthetic_only':True,'installed_inventory':installed,
    'archive_count':len(list(Path('/output/genetic-evidence').glob('*.zip'))),
    'real_native_response_calls':event.model_calls,'optimizer_searches':0,
    'synthetic_sync_wall_seconds':round(wall,6),'archive_commit_wall_seconds':round(elapsed[0],6),
    'source_fingerprints':{str(p.relative_to('/output')):hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in Path('/output').rglob('*') if p.is_file()},
    'max_process_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}))
'''
        helper = json.loads(command("run", *common,
            "--env", "EOS_DIR=/tmp/eos", "--env", "EOS_CONFIG_DIR=/tmp/eos",
            "--mount", f"type=volume,source={source},target=/output",
            "--mount", f"type=bind,source={ROOT / 'scripts/evidence_writer_synthetic.py'},target=/review/synthetic.py,readonly",
            "--mount", f"type=bind,source={ROOT / 'tests/fixtures/replay-synthetic-solution.json'},target=/review/template.json,readonly",
            "--entrypoint", "python", helper_image, "-c", driver).splitlines()[-1])
        for name, digest in helper["installed_inventory"]["source_sha256"].items():
            assert hashlib.sha256((ROOT / "src/eos_pv_helper" / (name+".py")).read_bytes()).hexdigest() == digest
        assert worker()["counts"]["pending"] == 1
        time.sleep(1.1)
        assert worker()["counts"]["verified"] == 1
        inspect_code = r'''
import hashlib,json
from pathlib import Path
from eos_pv_helper import dashboard,replay_contract
from eos_pv_helper.replay_worker_catalog import Catalog
source,root=Path('/archive'),Path('/replays')
catalog=Catalog(root).load(); assert len(catalog['plans'])==1
receipt_path=next((root/'receipts').glob('*.json')); receipt=json.loads(receipt_path.read_bytes())
solution=next(source.glob('solution-*.json')).read_bytes()
replay_contract.validate(catalog['plans'][0],solution,json.loads(solution))
before={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in source.rglob('*') if p.is_file()}
site=Path('/tmp/site'); site.mkdir()
assert dashboard.refresh(source,site,replay_file=root/'catalog.json')
view=json.loads(dashboard.DATA_PATTERN.search((site/'index.html').read_text())[1])
assert view['plans'][0]['rows'][0]['flow']['proof']==replay_contract.PROOF
after={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
       for p in source.rglob('*') if p.is_file()}
assert before==after
print(json.dumps({'receipt_sha256':receipt['sha256'],'receipt_mtime_ns':receipt_path.stat().st_mtime_ns,
    'metrics':receipt['metrics'],'original_hashes':before,'dashboard_native_flows':True}))
'''

        def inspect():
            return json.loads(command("run", *common,
                "--mount", f"type=volume,source={source},target=/archive,readonly",
                "--mount", f"type=volume,source={workspace},target=/replays,readonly",
                "--entrypoint", "python", worker_image, "-c", inspect_code).splitlines()[-1])

        first = inspect()
        assert first["original_hashes"] == helper.pop("source_fingerprints")
        assert worker()["counts"]["verified"] == 1
        assert inspect() == first  # Full source hashes plus immutable receipt/mtime.
        return {"contract": "eos-pv-helper/evidence-writer-container-review-v1", "synthetic_only": True,
                "helper_image_id": helper_image, "worker_image_id": worker_image,
                "installed_helper": helper, "native_worker_metrics": first["metrics"],
                "separate_readonly_worker": True, "originals_unchanged": True,
                "automatic_admission": True, "restart_did_not_replay": True,
                "dashboard_native_flows": first["dashboard_native_flows"],
                "no_helper_source_mounts": True, "production_activation_approved": False}
    finally:
        # Reap our own disposable container even if a Docker client times out.
        # No existing or operator-chosen container names can enter this list.
        for name in (prefix+"-run", prefix+"-init"):
            subprocess.run([*docker, "rm", "--force", name], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
        for name in created:
            assert name.startswith(prefix)
            command("volume", "rm", name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helper-image", required=True)
    parser.add_argument("--worker-image", required=True)
    parser.add_argument("--docker-context", default="default")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    raw = json.dumps(check(args.helper_image, args.worker_image, args.docker_context), indent=2)+"\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            handle.write(raw)
    print(raw)

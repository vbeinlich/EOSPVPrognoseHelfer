"""Code-only replay worker inventory. Never reads original archives or sidecars."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ".dockerignore",
    ".github/workflows/test.yaml",
    "src/eos_pv_helper/replay_worker.py",
    "src/eos_pv_helper/replay_worker_io.py",
    "src/eos_pv_helper/replay_worker_catalog.py",
    "src/eos_pv_helper/replay_worker_job.py",
    "replay-worker/Dockerfile",
    "replay-worker/compose.yaml",
    "replay-worker/constraints.txt",
    "scripts/unraid-native-replay-worker.sh",
    "scripts/unraid-dashboard-replay-catalog.sh",
    "scripts/replay_worker_container_smoke.py",
    "scripts/replay_worker_fixture.py",
    "scripts/replay_worker_private_review.py",
    "scripts/check_replay_worker_hashes.py",
]


def check(write=False):
    value = {
        "contract": "eos-pv-helper/replay-worker-code-inventory-v1",
        "base_commit": "f9362f53932594fa37800f1939405d47c9a6365f",
        "native_revision": "8a8cd43a1915668927eda5504b7de039c2e762b4",
        "contains_private_data": False,
        "production_activation_approved": False,
        "files": {name: hashlib.sha256((ROOT / name).read_bytes().replace(
            b"\r\n", b"\n")).hexdigest() for name in FILES},
    }
    raw = (json.dumps(value, indent=2, sort_keys=True)+"\n").encode()
    target = ROOT / "docs/REPLAY_WORKER_CODE_HASHES.json"
    if write:
        target.write_bytes(raw)
    elif target.read_bytes() != raw:
        raise ValueError("Replay worker code inventory differs")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    print(json.dumps(check(parser.parse_args().write), indent=2))

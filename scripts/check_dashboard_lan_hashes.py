"""Verify reviewable LAN deployment files; never deploy or change private data."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "deploy/dashboard/compose.yaml",
    "deploy/dashboard/nginx.conf",
    "deploy/dashboard/user-script.sh",
    "scripts/unraid-dashboard-preflight.sh",
    "scripts/unraid-dashboard-publish.sh",
    "scripts/dashboard_archive_hash_probe.py",
    "scripts/build_dashboard_lan_package.py",
)


def expected():
    return {
        "schema_version": 1,
        "base_commit": "8011a6d2849f5f17479dd1293f5806d39b3456e7",
        "activation_approved": False,
        "files": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FILES},
    }


def check():
    path = ROOT / "docs/DASHBOARD_LAN_CODE_HASHES.json"
    if json.loads(path.read_text()) != expected():
        raise SystemExit("LAN code hash manifest mismatch")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        (ROOT / "docs/DASHBOARD_LAN_CODE_HASHES.json").write_text(
            json.dumps(expected(), indent=2) + "\n", encoding="utf-8"
        )
    else:
        check()
    print("LAN deployment code hashes verified; no activation")

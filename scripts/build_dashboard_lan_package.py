"""Build a NEW private transfer folder. No deploy, replay or network activity."""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

from build_ems_dashboard import build
from check_dashboard_lan_hashes import ROOT, check

from eos_pv_helper.replay_contract import decode


def package(destination, revision, sidecar=None):
    check()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("An explicit review commit is required")
    approved = json.loads((ROOT / "docs/DASHBOARD_CODE_HASHES.json").read_text())
    bundle = build()
    wrapper = (ROOT / "scripts/unraid-ems-dashboard.sh").read_bytes()
    if (hashlib.sha256(bundle).hexdigest() != approved["dashboard_bundle_sha256"] or
            hashlib.sha256(wrapper).hexdigest() != approved["unraid_wrapper_sha256"]):
        raise ValueError("PR25 reader/wrapper bytes do not match the approved code manifest")
    files = {"tools/ems-dashboard-final.pyz": bundle, "tools/unraid-ems-dashboard.sh": wrapper}
    for name in ("unraid-dashboard-publish.sh", "unraid-dashboard-preflight.sh"):
        files["tools/" + name] = (ROOT / "scripts" / name).read_bytes()
    for name in ("compose.yaml", "nginx.conf", "user-script.sh"):
        files["server/" + name] = (ROOT / "deploy/dashboard" / name).read_bytes()
    for name in ("DASHBOARD_LAN_CODE_HASHES.json", "DASHBOARD_CODE_HASHES.json",
                 "DASHBOARD_UNRAID_LAN.md", "DASHBOARD_LAN_REVIEW.md"):
        files["docs/" + name] = (ROOT / "docs" / name).read_bytes()
    source_hashes = []
    if sidecar is not None:
        sidecar = Path(sidecar)
        if sidecar.is_symlink() or not sidecar.is_file():
            raise ValueError("Expected a regular private sidecar file")
        raw = sidecar.read_bytes()
        replay = decode(raw)
        source_hashes = [p["source_solution_sha256"] for p in replay["plans"]]
        files["replays/" + sidecar.name] = raw
    target = Path(destination)
    target.mkdir(mode=0o700)  # Must be NEW: prior reviewed transfer files are never replaced.
    for name, raw in files.items():
        file = target / name
        file.parent.mkdir(mode=0o700, exist_ok=True)
        with file.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
    manifest = {
        "schema_version": 1, "review_commit": revision, "activation_approved": False,
        "source_solution_hashes": source_hashes,
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
    }
    (target / "PACKAGE_HASHES.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (target / "PACKAGE_HASHES.json").chmod(0o600)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, help="New directory under a private parent")
    parser.add_argument("--review-commit", required=True)
    parser.add_argument("--private-replays", help="Optional already checked sidecar; never recalculated")
    args = parser.parse_args()
    manifest = package(args.destination, args.review_commit, args.private_replays)
    print(json.dumps({"files": len(manifest["files"]), "activation_approved": False}))

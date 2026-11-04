"""Deterministic code-only dashboard/producer hashes, without private replay data."""

import argparse
import hashlib
import json
from pathlib import Path

from build_ems_dashboard import build

ROOT = Path(__file__).resolve().parents[1]


def check(write=False):
    result = {
        "schema_version": 1,
        "dashboard_bundle_sha256": hashlib.sha256(build()).hexdigest(),
        "unraid_wrapper_sha256": hashlib.sha256(
            (ROOT / "scripts/unraid-ems-dashboard.sh").read_bytes()
        ).hexdigest(),
        "offline_exporter_sha256": hashlib.sha256(
            (ROOT / "src/eos_pv_helper/replay_export.py").read_text(encoding="utf-8-sig").encode()
        ).hexdigest(),
        "contains_measurements": False,
        "distribution_approved": False,
    }
    raw = (json.dumps(result, indent=2) + "\n").encode()
    target = ROOT / "docs/DASHBOARD_CODE_HASHES.json"
    if write:
        target.write_bytes(raw)
    elif not target.is_file() or target.read_bytes() != raw:
        raise ValueError("Dashboard code hashes differ; update in the reviewed development branch")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    print(json.dumps(check(parser.parse_args().write), indent=2))

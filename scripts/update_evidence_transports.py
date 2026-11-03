"""Development-only deterministic engine embedding and public code-hash manifest.

No network, Docker, data exports or approvals. --write edits only development code.
Without --write every generated transport/hash must already match (CI gate).
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from build_plan_inspector import build

ROOT = Path(__file__).resolve().parents[1]


def update(write=False):
    source = (ROOT/"src/eos_pv_helper/historical.py").read_text(encoding="utf-8")
    engine = source.rstrip("\n")
    digest = hashlib.sha256(engine.encode()).hexdigest()
    path = ROOT/"scripts/unraid-doctor-export.sh"
    wrapper = path.read_text(encoding="utf-8")
    prefix, rest = wrapper.split("historical_engine=$(cat <<'PY_ENGINE'\n", 1)
    _, suffix = rest.split("\nPY_ENGINE\n", 1)
    expected = re.sub(r"^engine_sha256=[0-9a-f]{64}$", "engine_sha256="+digest,
        prefix+"historical_engine=$(cat <<'PY_ENGINE'\n"+engine+"\nPY_ENGINE\n"+suffix, flags=re.M)
    if write:
        path.write_bytes(expected.encode())
    elif path.read_bytes() != expected.encode():
        raise ValueError("Embedded engine, hash or line endings differ; run --write in development")
    bundle = build()
    manifest = {"validation_contract": "eos-pv-helper/event-evidence-v2",
        "binding_contract": "eos-pv-helper/solver-input-binding-v1",
        "historical_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
        "historical_embedded_sha256": digest,
        "doctor_wrapper_sha256": hashlib.sha256(expected.encode()).hexdigest(),
        "inspector_wrapper_sha256": hashlib.sha256((ROOT/"scripts/unraid-plan-inspector.sh").read_bytes()).hexdigest(),
        "inspector_bundle_sha256": hashlib.sha256(bundle).hexdigest(), "inspector_bundle_bytes": len(bundle),
        "contains_measurements": False, "distribution_approved": False}
    output = ROOT/"docs/INPUT_BINDING_TRANSPORTS.json"
    raw = (json.dumps(manifest, indent=2)+"\n").encode()
    if write:
        output.write_bytes(raw)
    elif output.read_bytes() != raw:
        raise ValueError("Code hash manifest differs from reviewed transports")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    print(json.dumps(update(parser.parse_args().write), indent=2))

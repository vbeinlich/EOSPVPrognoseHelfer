"""Code-only installed-image capability inventory; never opens /output or configuration."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from eos_pv_helper import evidence, historical
from eos_pv_helper.economics_native import EOS_REVISION

MODULES = ("evidence", "historical", "doctor", "sync", "event_context", "storage", "economics", "inputs")


def inventory():
    sources = {}
    for name in MODULES:
        source = Path(importlib.util.find_spec("eos_pv_helper."+name).origin)
        assert source.is_file()
        sources[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    assert historical.VALIDATION_CONTRACT == "eos-pv-helper/event-evidence-v2"
    assert evidence.REPLAY_ADMISSION == "eos-pv-helper/replay-ready-archive-v1"
    assert evidence.enabled({}) is False and evidence.enabled({"evidence": {"enabled": True}})
    return {"contract": "eos-pv-helper/evidence-writer-image-v1", "source_sha256": sources,
            "archive_validation_contract": historical.VALIDATION_CONTRACT,
            "replay_admission_contract": evidence.REPLAY_ADMISSION, "native_revision": EOS_REVISION,
            "archive_path": "genetic-evidence/<event-version>.zip", "artifact_count": 7,
            "evidence_requires_explicit_enable": True, "production_activation_approved": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = (json.dumps(inventory(), indent=2, sort_keys=True)+"\n").encode()
    if args.output:
        with args.output.open("xb") as handle:
            handle.write(raw)
    else:
        print(raw.decode(), end="")

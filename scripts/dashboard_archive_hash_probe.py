"""Diagnose saved GET vs archive serialization; never changes inputs or sidecars.

An optional NEW local file is written only if its complete byte hash already
matches an independently supplied archive hash. This is NOT a NAS download.
Run only on the private review workstation, never during an HTML refresh.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def recover(source, expected, destination=None):
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Expected SHA-256 must be supplied independently")
    source = Path(source)
    if source.is_symlink() or source.stat().st_size > 32_000_000:
        raise ValueError("Expected a regular bounded saved response")
    original = source.read_bytes()
    parsed = json.loads(original)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a saved solution object")
    # Exact existing storage.atomic_json format; no semantic fields are changed.
    candidate = (json.dumps(parsed, indent=2, allow_nan=False) + "\n").encode("utf-8")
    digest = hashlib.sha256(candidate).hexdigest()
    if digest != expected:
        raise ValueError("Archive hash mismatch: no file or sidecar written")
    if destination is not None:
        # Exclusive creation: no historical file, prior sidecar or input overwritten.
        with Path(destination).open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
    return {
        "provenance": "archive-format reconstruction; not a direct NAS download",
        "source_get_sha256": hashlib.sha256(original).hexdigest(),
        "archive_bytes_sha256": digest,
        "archive_bytes": len(candidate),
        "matches_independently_supplied_hash": True,
        "json_structurally_equal": json.loads(candidate) == parsed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saved-response", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--write-new", help="Optional new private file; NEVER an original or sidecar")
    args = parser.parse_args()
    try:
        result = recover(args.saved_response, args.expected_sha256, args.write_new)
    except (OSError, ValueError):
        raise SystemExit("Archive hash/provenance check failed; no input modified") from None
    print(json.dumps(result, sort_keys=True))

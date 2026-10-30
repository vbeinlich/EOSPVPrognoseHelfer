"""Preserve exact corresponding GCC sources for wheel-bundled libquadmath.

Never replaces binaries. Unknown wheel payloads fail closed rather than inheriting
a source mapping from a similar filename. This is build tooling, not a runtime API.
"""

import argparse
import hashlib
import json
import re
import sysconfig
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

ALLOWED_ORIGINS = {"vault.centos.org", "repo.almalinux.org"}
MAX_BYTES = 100_000_000


def fetch(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_ORIGINS or parts.username:
        raise ValueError("Unapproved native source origin")
    with urlopen(url, timeout=180) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname not in ALLOWED_ORIGINS:
            raise ValueError("Unapproved native source redirect")
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Oversized native source archive")
    return raw


def collect(site, output, manifest, *, download=fetch, mapping_only=False):
    site, output = Path(site), Path(output)
    rows = {entry["bundled_sha256"]: entry for entry in manifest["libraries"]}
    matches, selected = [], {}
    for path in sorted(site.glob("**/*libquadmath*.so*")):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in rows:
            raise ValueError("Unknown libquadmath payload; audited source mapping required")
        row = rows[digest]
        selected[row["source_id"]] = manifest["sources"][row["source_id"]]
        matches.append({"file": path.relative_to(site).as_posix(), "sha256": digest,
                        "source_id": row["source_id"], "build_id": row["build_id"]})
    if not matches:
        raise ValueError("Expected wheel-bundled libquadmath is absent")
    # Validate every binary first. An unknown payload cannot trigger a guessed download.
    output.mkdir(parents=True, exist_ok=True)
    for source in selected.values():
        name = source["filename"]
        if not re.fullmatch(r"gcc-[A-Za-z0-9_.+-]+\.src\.rpm", name):
            raise ValueError("Invalid source archive filename")
        if mapping_only:
            continue
        target = output / name
        if target.is_symlink():
            raise ValueError("Unsafe native source cache")
        raw = target.read_bytes() if target.exists() else download(source["url"])
        if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("Native source archive hash differs")
        if not target.exists():
            target.write_bytes(raw)
    result = {"schema_version": 1, "libraries": matches, "sources": selected,
              "binary_replacements": False, "archives_in_image": not mapping_only,
              "source_mapping_reviewed_date": "2026-10-30"}
    (output / "sources.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=sysconfig.get_path("platlib"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "licenses/native-sources.json")
    parser.add_argument("--mapping-only", action="store_true", help="Sources go into the separately verified release source bundle")
    args = parser.parse_args()
    result = collect(args.site, args.output, json.loads(args.manifest.read_text()), mapping_only=args.mapping_only)
    print("Preserved", len(result["sources"]), "exact GCC source RPMs for", len(result["libraries"]), "bundled libraries")

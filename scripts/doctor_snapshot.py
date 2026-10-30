"""Export only existing acceptance files to private stdout ZIP. No HTTP or writes.

Run with the existing helper's Python via stdin; no package upgrade is required.
Redirect stdout to a NEW private file outside the live output directory. Do not
publish this archive: it contains private measurements and diagnostics.
"""

import argparse
import fcntl
import hashlib
import io
import json
import re
import sys
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

MAX_BYTES = 8_000_000


def export(directory, *, config=None, clock=lambda: datetime.now(UTC)):
    directory = Path(directory)
    lock = directory / "sync.lock"
    if lock.is_symlink() or not lock.is_file():
        raise ValueError("Existing sync lock unavailable")
    with lock.open("rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Sync in progress; retry export later without stopping it") from None
        captured = clock().isoformat()

        def read(name):
            path = directory / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
                raise ValueError("Missing or unsafe snapshot file")
            with path.open("rb") as source:
                raw = source.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("Oversized snapshot file")
            return raw

        report = read("sync-report.json")
        version = json.loads(report).get("event", {}).get("version", "")
        if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{64}", version):
            raise ValueError("Current report has no accepted event version; export later")
        files = {"sync-report.json": report, "sync-state.json": read("sync-state.json"),
                 "prices.json": read("prices.json"),
                 "solution-" + version + ".json": read("solution-" + version + ".json")}
        settings = config or {}
        soc = settings.get("soc", {})
        age, power = soc.get("max_age_seconds", 300), soc.get("max_abs_power_w", 20000)
        if (isinstance(age, bool) or not isinstance(age, (int, float)) or not 0 < age <= 300
                or isinstance(power, bool) or not isinstance(power, (int, float)) or not 0 < power <= 100000):
            raise ValueError("Invalid snapshot validation constraints")
        manifest = {"schema_version": 1, "captured_at_utc": captured,
            "timezone": settings.get("timezone", "Europe/Berlin"), "event_version": version,
            "validation_constraints": {"max_age_seconds": age, "max_abs_power_w": power},
            "configured_constraints_read": config is not None,
            "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
            "scope": "private historical snapshot; not a live measurement"}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("snapshot.json", json.dumps(manifest, indent=2))
            for name, raw in files.items():
                archive.writestr(name, raw)
        return stream.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/output")
    parser.add_argument("--config", help="Read only validation limits; no secrets are exported")
    args = parser.parse_args()
    try:
        config = tomllib.loads(Path(args.config).read_text()) if args.config else None
        raw = export(args.source, config=config)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise SystemExit("Private snapshot unavailable; no source files were changed") from None
    sys.stdout.buffer.write(raw)

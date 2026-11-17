"""Exact, offline join of complementary original interval exports; no arithmetic."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from .energy_data import EnergyDataError, canonical, timestamp

KEYS = ("start_utc", "end_utc")


def join_csv(left_raw, right_raw, *, start, end, interval_seconds=3600):
    if type(interval_seconds) is not int or interval_seconds not in (900, 3600):
        raise EnergyDataError("Unsupported original interval grid")
    beginning, stop = timestamp(start, {}), timestamp(end, {})
    tables, headers = [], []
    for raw in (left_raw, right_raw):
        if not isinstance(raw, bytes) or len(raw) > 64_000_000:
            raise EnergyDataError("Missing or oversized original CSV")
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        names = reader.fieldnames
        if not names or len(set(names)) != len(names) or any(k not in names for k in KEYS):
            raise EnergyDataError("Original CSV headers invalid")
        table = {}
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise EnergyDataError("Malformed original CSV row")
            key = tuple(timestamp(row[k], {}) for k in KEYS)
            if key in table or (key[1] - key[0]).total_seconds() != interval_seconds:
                raise EnergyDataError("Duplicate or nonmatching original interval")
            table[key] = row
            if len(table) > 35136:
                raise EnergyDataError("Original interval count exceeds bounded join")
        tables.append(table)
        headers.append(names)
    if tables[0].keys() != tables[1].keys() or not tables[0]:
        raise EnergyDataError("Both sources must cover exactly the same interval identities")
    keys = sorted(tables[0])
    if (keys[0][0] != beginning or keys[-1][1] != stop
            or any(a[1] != b[0] for a, b in zip(keys, keys[1:]))):
        raise EnergyDataError("Original interval coverage has gaps or overlap")
    collision = (set(headers[0]) & set(headers[1])) - set(KEYS)
    if collision:
        raise EnergyDataError("Complementary columns collide; refusing to replace original values")
    columns = headers[0] + [k for k in headers[1] if k not in KEYS]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for key in keys:
        writer.writerow({**tables[0][key], **{k: v for k, v in tables[1][key].items() if k not in KEYS}})
    joined = stream.getvalue().encode("utf-8")
    return joined, {"status": "joined", "intervals": len(keys),
                    "start_utc": beginning.isoformat(), "end_utc": stop.isoformat(),
                    "source_sha256": [hashlib.sha256(raw).hexdigest() for raw in (left_raw, right_raw)],
                    "joined_sha256": hashlib.sha256(joined).hexdigest(),
                    "columns_recalculated": False, "original_load_column_scope": "unchanged"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--supplement", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--interval-seconds", type=int, default=3600)
    parser.add_argument("--output", required=True, help="New private directory")
    args = parser.parse_args(argv)
    try:
        output = Path(args.output)
        if output.exists() or output.is_symlink() or not output.parent.is_dir():
            raise EnergyDataError("Output must be an isolated new directory")
        raw_sources = []
        for path in (Path(args.base), Path(args.supplement)):
            if path.is_symlink():
                raise EnergyDataError("Original source cannot be a symlink")
            with path.open("rb") as handle:
                raw_sources.append(handle.read(64_000_001))
        joined, audit = join_csv(*raw_sources, start=args.start, end=args.end,
                                 interval_seconds=args.interval_seconds)
        artifacts = {"base-original.csv": raw_sources[0], "supplement-original.csv": raw_sources[1],
                     "joined.csv": joined, "join-audit.json": canonical(audit)}
        output.mkdir(mode=0o700)
        for name, raw in artifacts.items():
            with (output / name).open("xb") as handle:
                handle.write(raw)
        with (output / "manifest.json").open("xb") as handle:
            handle.write(canonical({"complete": True, "artifacts_sha256": {
                name: hashlib.sha256(raw).hexdigest() for name, raw in artifacts.items()}}))
        print(json.dumps({"status": "joined", "intervals": audit["intervals"]}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, csv.Error):
        print("Exact interval join failed; original sources unchanged")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

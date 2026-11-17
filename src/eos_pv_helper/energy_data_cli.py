"""Prepare existing local sensor exports with the shared measurement adapter."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from .energy_data import EnergyDataError, as_actuals, canonical, observations_from_ha, prepare


def export_csv(data):
    """Wh, EUR and original SOC timestamps, with per-field quality beside values."""
    rows = data["rows"]
    fields = [k for k in rows[0] if k not in ("quality", "issues")]
    quality_fields = sorted({k for r in rows for k in r["quality"]})
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields + [k + "_quality" for k in quality_fields] + ["issues"])
    writer.writeheader()
    for row in rows:
        writer.writerow({**{k: row.get(k) for k in fields},
                         **{k + "_quality": row["quality"].get(k, {}).get("status", "incomplete")
                            for k in quality_fields}, "issues": "|".join(row["issues"])})
    return stream.getvalue().encode("utf-8")


def read_observations(raw, kind, config=None):
    if len(raw) > 64_000_000:
        raise EnergyDataError("Original export too large")
    if kind in ("csv", "wide_csv"):
        table = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")),
                               delimiter=(config or {}).get("delimiter", ","))
        if not table.fieldnames or len(set(table.fieldnames)) != len(table.fieldnames):
            raise EnergyDataError("Duplicate or missing source headers")
        rows = list(table)
        if kind == "csv":
            return [{k: v for k, v in r.items() if v != ""} for r in rows]
        observations = []
        for row in rows:
            for spec in config["metrics"].values():
                for source in spec["sources"]:
                    columns = source.get("csv")
                    if not columns or columns["value"] not in row:
                        continue  # Absent quantities stay absent in the shared audit.
                    value = row[columns["value"]]
                    if config.get("decimal_separator", ".") == "," and isinstance(value, str):
                        if "." in value:
                            raise EnergyDataError("Ambiguous CSV numeric convention")
                        value = value.replace(",", ".")
                    record = {"entity_id": source["entity_id"], "unit": source["unit"],
                              "value": value if value != "" else None, "original": dict(row)}
                    if "coverage" in columns:
                        record["mean_power_coverage"] = row.get(columns["coverage"])
                    for key in ("at", "start", "end", "received_at"):
                        if key in columns:
                            record[key] = row[columns[key]]
                    observations.append(record)
        return observations
    def pairs(items):
        data = {}
        for k, v in items:
            if k in data:
                raise EnergyDataError("Duplicate JSON key")
            data[k] = v
        return data
    parsed = json.loads(raw, object_pairs_hook=pairs)
    return observations_from_ha(parsed) if kind == "ha_history" else parsed["observations"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--input-kind", choices=("json", "csv", "wide_csv", "ha_history"), default="json")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--as-of", required=True, help="Explicit arrival/event watermark with UTC offset")
    parser.add_argument("--output", required=True, help="New private directory; never overwrite originals")
    args = parser.parse_args(argv)
    try:
        source, target = Path(args.input), Path(args.output)
        if target.exists() or target.is_symlink() or not target.parent.is_dir() or source.is_symlink():
            raise EnergyDataError("Input/output isolation invalid")
        with source.open("rb") as handle:
            raw = handle.read(64_000_001)
        config = json.loads(Path(args.mapping).read_bytes())
        data = prepare(read_observations(raw, args.input_kind, config), config,
                       args.start, args.end, as_of=args.as_of)
        data["source_file_sha256"] = hashlib.sha256(raw).hexdigest()
        artifacts = {"prepared.json": canonical(data), "corrected.csv": export_csv(data),
                     "audit.json": canonical(data["audit"]), "original-export.bin": raw,
                     "mapping.json": canonical(config)}
        if data["data_kind"] == "measured" and data["audit"]["status"] == "passed":
            artifacts["plan-actual.json"] = canonical(as_actuals(data))
        target.mkdir(mode=0o700)
        for name, content in artifacts.items():
            with (target / name).open("xb") as handle:
                handle.write(content)
        manifest = {"complete": True, "artifacts_sha256": {
            k: hashlib.sha256(v).hexdigest() for k, v in artifacts.items()}}
        with (target / "manifest.json").open("xb") as handle:
            handle.write(canonical(manifest))
        print(json.dumps({"status": data["audit"]["status"], "intervals": len(data["rows"]),
                          "complete_intervals": data["audit"]["complete_intervals"]}))
        # Diagnostic artifacts survive incomplete input; exit status never calls it a pass.
        return 0 if data["audit"]["status"] == "passed" else 3
    except (OSError, ValueError, KeyError, TypeError, csv.Error):
        print("Energy preparation failed: invalid source, mapping or output; originals unchanged.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

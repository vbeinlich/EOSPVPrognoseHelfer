"""One isolated offline run. Outputs are immutable; no production path defaults."""

import argparse
import json
import os
from pathlib import Path

from .adapter import journal
from .config import Config, SimulationError
from .engine import simulate
from .inputs import canonical, digest, from_actuals, from_eos, read_json


def run(args):
    source = Path(args.input).resolve(strict=True)
    output = Path(args.output)
    # New run directories only. Neither old reports nor source data are replaced.
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise SimulationError("Output must be a new directory under an existing parent")
    if args.input_kind == "history_csv":
        import hashlib

        with source.open("rb") as handle:
            csv_raw = handle.read(16_000_001)
        if len(csv_raw) > 16_000_000:
            raise SimulationError("Historical CSV exceeds the bounded import size")
        input_sha, raw_input = hashlib.sha256(csv_raw).hexdigest(), None
    else:
        raw_input, input_sha = read_json(source)
    config_data, config_sha = read_json(args.config) if args.config else ({}, digest({}))
    config = Config.from_dict(config_data)
    context, context_sha = read_json(args.context) if args.context else ({}, None)
    if args.input_kind == "eos":
        data = from_eos(raw_input, input_sha, context=context)
    elif args.input_kind == "actuals":
        data = from_actuals(raw_input, input_sha, context=context)
    elif args.input_kind == "history_csv":
        from .history import import_csv

        data = import_csv(csv_raw, context)
    elif args.input_kind == "prepared":
        from .prepared import from_prepared

        data = from_prepared(raw_input, context)
    else:
        data = raw_input
    if args.phase2:
        from .comparison import compare

        result = compare(data, config)
    else:
        result = simulate(data, config)
    result["input_file_sha256"] = input_sha
    result["config_file_sha256"] = config_sha
    result["context_file_sha256"] = context_sha
    # Import only the existing static renderer, never the sync/app/device paths.
    from eos_pv_helper.dashboard_view import render

    preview = render({"dashboard_schema": 1, "plans": [], "ranges": {},
                      "latest_sync_status": "SIM offline", "checked_at_utc": None,
                      "synthetic_only": data["data_kind"] == "synthetic",
                      "maxxicharge_sim": result})
    artifacts = {
        "simulation.json": canonical(result),
        "index.html": preview.encode("utf-8"),
        "mqtt-sim.jsonl": b"\n".join(canonical(entry) for entry in journal(result)) + b"\n",
        "normalized-input.json": canonical(data),
    }
    # Validate/render fully before making anything visible. A completion manifest
    # is written last; consumers use only directories containing that manifest.
    output.mkdir(mode=0o700)
    for name, raw in artifacts.items():
        with (output / name).open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    import hashlib

    manifest = {"mode": "SIM", "complete": True,
                "artifacts_sha256": {name: hashlib.sha256(raw).hexdigest()
                                     for name, raw in artifacts.items()}}
    with (output / "manifest.json").open("xb") as handle:
        handle.write(canonical(manifest))
    print(json.dumps({"mode": "SIM", "complete": True, "devices_commanded": False,
                      "coverage_hours": result["coverage_hours"],
                      "data_kind": result["data_kind"], "input_sha256": input_sha}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Existing local input, mounted read-only")
    parser.add_argument("--input-kind", choices=("normalized", "eos", "actuals", "history_csv", "prepared"),
                        default="normalized")
    parser.add_argument("--config", help="Simulator-only JSON configuration")
    parser.add_argument("--context", help="Explicit offline EOS/measurement modelling context")
    parser.add_argument("--output", required=True, help="New isolated output directory")
    parser.add_argument("--phase2", action="store_true", help="Manufacturer-limited A/B/C comparison")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (SimulationError, OSError, KeyError, TypeError, ValueError):
        print("SIM failed: invalid/missing input, context or isolated output; no device action.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

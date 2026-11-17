"""Compare a PRIVATE prepared 120-hour export against operator aggregate evidence.

This does not manufacture an hourly fixture or grant historical model acceptance.
"""

import argparse
import json
from pathlib import Path

from eos_pv_helper.energy_data import EnergyDataError, verify_prepared

ROOT = Path(__file__).resolve().parents[1]


def check(data, reference):
    checked = verify_prepared(data)
    rows, audit = checked["rows"], checked["audit"]
    if (checked["data_kind"] != "measured" or audit["status"] != "passed"
            or len(rows) != reference["intervals"]
            or rows[0]["start_utc"] != reference["start_utc"]
            or rows[-1]["end_utc"] != reference["end_utc"]):
        raise EnergyDataError("Regression needs complete measured original reference hours")
    deltas = {}
    for key, expected in reference["totals"].items():
        if audit["totals_covered_intervals"].get(key) != len(rows):
            raise EnergyDataError("Reference quantity incomplete: " + key)
        delta = audit["totals"][key] - expected
        tolerance = reference["tolerances"].get(key, reference["tolerances"]["default_wh"])
        if abs(delta) > tolerance:
            raise EnergyDataError("Original measurements differ from aggregate reference: " + key)
        deltas[key] = delta
    return {"status": "passed", "reference_deltas": deltas,
            "original_intervals": len(rows), "historical_acceptance_passed": False,
            "message": "Original hourly aggregate regression passed; historical SOC/model admission remains separate"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--reference", default=str(ROOT / "tests/fixtures/energy-november-reference.json"))
    args = parser.parse_args(argv)
    try:
        print(json.dumps(check(json.loads(Path(args.prepared).read_bytes()),
                               json.loads(Path(args.reference).read_bytes())), sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print("Original 120-hour energy regression failed or original data missing; no historical acceptance.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

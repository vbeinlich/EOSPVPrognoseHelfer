"""Generate a NEW synthetic economic UI fixture using native forward simulation."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"tests"))

from test_economics import packet  # noqa: E402

from eos_pv_helper.economics_report import from_packet  # noqa: E402
from eos_pv_helper.plan_view import render  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", required=True, help="NEW synthetic HTML path outside input volumes")
    args = parser.parse_args()
    report = from_packet(packet(), scaled_load=True)
    c = report["plans"][0]["comparison"]
    assert c["status"] == "calculated", c
    assert abs(c["additional_savings_eur"]) < 1e-9
    assert c["baseline"]["end_soc_percent"] == 10
    assert c["genetic"]["end_soc_percent"] == 40
    if args.html == "-":
        sys.stdout.buffer.write(render(report).encode("utf-8"))
    else:
        with Path(args.html).open("x", encoding="utf-8") as output:
            output.write(render(report))
    print(json.dumps({"passed": True, "synthetic_only": True, "optimizer_invoked": False,
                      "real_savings_claim": False, "native_replay_verified": True}),
          file=sys.stderr if args.html == "-" else sys.stdout)


if __name__ == "__main__":
    main()

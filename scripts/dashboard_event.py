"""Append one synthetic fixture event and export it; never calls EOS or a solver."""

import argparse
from pathlib import Path

from dashboard_fixture import event

from eos_pv_helper.dashboard import refresh

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    event(Path(args.source))
    if not refresh(args.source, args.destination):
        raise SystemExit("Synthetic event could not be exported")

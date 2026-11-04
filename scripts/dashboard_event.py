"""Append one synthetic fixture event and export it; never calls EOS or a solver."""

import argparse
import subprocess
from pathlib import Path

from dashboard_fixture import event

from eos_pv_helper.dashboard import refresh

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--publication-tools")
    parser.add_argument("--publication-destination")
    args = parser.parse_args()
    if bool(args.publication_tools) != bool(args.publication_destination):
        parser.error("Both publication paths are required together")
    event(Path(args.source))
    if args.publication_tools:
        # Exercise the actual reviewed publisher, including private 0600 -> public
        # 0644 atomic transition. This driver is ONLY for synthetic test fixtures.
        script = Path(__file__).with_name("unraid-dashboard-publish.sh")
        subprocess.run(
            ["bash", str(script), args.publication_tools,
             args.destination, args.publication_destination],
            check=True, timeout=70,
        )
    elif not refresh(args.source, args.destination):
        raise SystemExit("Synthetic event could not be exported")

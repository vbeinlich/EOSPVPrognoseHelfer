"""Synthetic UTC/DST cases for native flow replay browser acceptance."""

import argparse
import json
from pathlib import Path

from replay_fixture import build


def generate(destination):
    rows = []
    for seconds in (900, 3600):
        for name, start in (
            ("spring", "2026-03-29T00:00:00+00:00"),
            ("autumn", "2026-10-25T00:00:00+00:00"),
        ):
            root = Path(destination) / f"{name}-{seconds}"
            build(root, seconds=seconds, start=start)
            rows.append({"seconds": seconds, "start": start, "directory": str(root)})
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    print(json.dumps(generate(parser.parse_args().destination)))

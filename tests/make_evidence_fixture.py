"""Create only synthetic auto-archived evidence for real-container compatibility.

Uses the real sync writer and mocked HTTP. Never contacts EOS or runs GENETIC.
No real measurements, archives, configuration or credentials are consumed.
"""

import argparse
import json
import shutil
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import conftest
import pytest
from test_evidence import archive, build_case, tick


def create(destination):
    destination = Path(destination)
    destination.mkdir(mode=0o755)  # Fail rather than overwrite any existing fixture.
    working = destination / "synthetic-writer"
    working.mkdir(mode=0o700)
    with pytest.MonkeyPatch.context() as patch:
        config = conftest.config.__wrapped__(working)
        case = build_case(config, patch)
        patch.setenv("DRY_RUN", "false")
        assert tick(case)["evidence"]["status"] == "archived"
        original = archive(case).read_bytes()
        local = case["now"].astimezone(ZoneInfo("Europe/Berlin"))
        cutoff = (local.replace(hour=0, minute=0, second=0)+timedelta(days=1)).timestamp()
        case["evcc"]["forecast"]["grid"] = [r for r in case["evcc"]["forecast"]["grid"] if r[0] < cutoff]
        assert tick(case)["event"]["status"] == "waiting-publication"
        assert archive(case).read_bytes() == original
    # Only diagnostic COPIES of synthetic data are made accessible to container UID 10001.
    inspection = destination / "inspection"
    inspection.mkdir(mode=0o755)
    for name in ("sync-state.json", "sync-report.json", "sync.lock"):
        shutil.copyfile(working / name, inspection / name)
    for source in working.glob("solution-*.json"):
        shutil.copyfile(source, inspection / source.name)
    (destination / "snapshot.zip").write_bytes(original)
    (destination / "limits.toml").write_text('timezone="Europe/Berlin"\n[soc]\nmax_age_seconds=300\nmax_abs_power_w=20000\n')
    for root in (destination, inspection):
        root.chmod(0o755)
        for path in root.iterdir():
            if path.is_file():
                path.chmod(0o444)
    return {"synthetic_only": True, "archive_unchanged_after_waiting": True,
            "mocked_optimize_requests": len([c for c in case["calls"] if c[0] == "POST"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    print(json.dumps(create(parser.parse_args().destination)))

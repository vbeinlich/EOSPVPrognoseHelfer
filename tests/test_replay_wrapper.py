"""Full host wrapper framing of a separate replay file, including last-good recovery."""

import json
from pathlib import Path

from test_dashboard import packet
from test_dashboard_wrapper import harness  # noqa: F401

FIXTURES = Path(__file__).parent / "fixtures"


def test_wrapper_reads_sidecar_without_native_engine_and_keeps_last_good(harness):  # noqa: F811
    source, dest, _, run = harness
    raw = (FIXTURES / "replay-synthetic-solution.json").read_bytes()
    solution = json.loads(raw)
    state = json.loads((source / "sync-state.json").read_text())
    version = max(state["events"], key=lambda v: state["events"][v]["start_utc"])
    state["events"][version].update(
        start_utc=solution["start_solution_datetime"],
        claimed_at_utc=solution["start_solution_datetime"],
        interval_seconds=solution["interval_seconds"],
    )
    (source / f"solution-{version}.json").write_bytes(raw)
    (source / "sync-state.json").write_text(json.dumps(state))
    replay = dest.parent / "replays.json"
    replay.write_bytes((FIXTURES / "replay-synthetic-sidecar.json").read_bytes())
    assert run(extra=("--replays", str(replay))).returncode == 0
    before = packet(dest / "index.html")
    selected = next(p for p in before["plans"] if p["version"] == version)
    assert selected["flow_replay"]["status"] == "verified"
    assert selected["rows"][0]["flow"]["pv_wh"] > 0
    assert selected["rows"][0]["flow"]["grid_wh"] > 0
    replay.write_text('{"truncated":')
    assert run(extra=("--replays", str(replay))).returncode == 2
    after = packet(dest / "index.html")
    assert after["plans"] == before["plans"] and after["update_error"]

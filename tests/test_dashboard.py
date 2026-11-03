"""Dashboard acceptance: offline/read-only, provenance, time ownership and atomic recovery."""

import copy
import fcntl
import hashlib
import json
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from dashboard_fixture import event, make

from eos_pv_helper import dashboard as dashboard
from eos_pv_helper import dashboard_view, economics

NOW = datetime(2026, 11, 1, 13, tzinfo=UTC)


@pytest.fixture
def source(tmp_path):
    return make(tmp_path / "source")


def fingerprint(root):
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def packet(path):
    text = path.read_text()
    return json.loads(dashboard.DATA_PATTERN.search(text)[1])


def change_solution(source, fn):
    path = sorted(source.glob("solution-*.json"))[0]
    value = json.loads(path.read_text())
    fn(value)
    path.write_text(json.dumps(value))
    return path


def test_no_network_no_live_inputs_no_simulation_no_source_writes(source, monkeypatch):
    before = fingerprint(source)
    original = Path.open

    def guarded(path, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        assert path.name not in ("prices.json", "forecast.json", "soc.json", "config.toml")
        return original(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    monkeypatch.setattr(economics, "evaluate", lambda *a, **k: pytest.fail("simulation forbidden"))
    report = dashboard.prepare(dashboard.collect(source, now=NOW))
    html = dashboard_view.render(report)
    assert len(report["plans"]) == 3
    assert report["latest_sync_status"] == "waiting-publication"
    monkeypatch.setattr(Path, "open", original)
    assert before == fingerprint(source)
    assert "PRIVATE-CANARY" not in html and "NEVER-READ" not in html
    assert "connect-src 'none'" in html and 'http-equiv="refresh"' in html
    assert all(p["model_comparison"]["advantage_eur"] is None for p in report["plans"])


def test_permissions_never_become_energy(source):
    change_solution(source, lambda s: s["result"].pop("battery_flow_energy_basis"))
    report = dashboard.collect(source, now=NOW)
    plan = next(p for p in report["plans"] if p["rows"][0]["flow"]["proof"] == "unavailable")
    assert any(r["controls"]["ac_charge"] > 0 for r in plan["rows"])
    assert all(r["flow"]["charge_wh"] is None and r["flow"]["pv_wh"] is None for r in plan["rows"])


def test_unknown_origin_stays_unknown_even_when_pv_or_ac_permission_exists(source):
    report = dashboard.collect(source, now=NOW)
    latest = report["plans"][0]
    assert latest["start_utc"].startswith("2026-10-31")
    assert all(r["flow"]["pv_wh"] is None and r["flow"]["grid_wh"] is None for r in latest["rows"])
    assert sum(r["flow"]["unknown_wh"] for r in latest["rows"]) > 0
    older = report["plans"][1]
    assert sum(r["flow"]["grid_wh"] for r in older["rows"]) == 2640
    assert all(r["flow"]["proof"] == "stored_source_split" for r in older["rows"])


@pytest.mark.parametrize(
    "mutation", ["negative", "nan", "source_sum", "short", "partial_split", "control"]
)
def test_bad_numeric_contract_rejected(source, mutation):
    def mutate(s):
        r = s["result"]
        if mutation == "negative":
            r["battery_charge_dc_wh_per_hour"][0] = -1
        elif mutation == "nan":
            r["battery_charge_dc_wh_per_hour"][0] = float("nan")
        elif mutation == "short":
            r["battery_charge_dc_wh_per_hour"].pop()
        elif mutation == "partial_split":
            r["battery_grid_charge_dc_wh_per_hour"] = [0] * 96
        elif mutation == "source_sum":
            r["battery_pv_charge_dc_wh_per_hour"] = [10000] * 96
            r["battery_grid_charge_dc_wh_per_hour"] = [0] * 96
        else:
            s["ac_charge"][0] = 2

    change_solution(source, mutate)
    with pytest.raises(ValueError):
        dashboard.collect(source, now=NOW)


def test_overlapping_forecasts_count_energy_once_and_exclude_tail(source):
    report = dashboard.collect(source, now=NOW)
    version = event(source)
    report = dashboard.collect(source, now=NOW)
    new = next(p for p in report["plans"] if p["version"] == version)
    segments = dashboard.timeline(report["plans"], 7)
    active = [r for r in segments if not r.get("gap")]
    assert all(a["end_utc"] == b["start_utc"] for a, b in zip(segments, segments[1:]))
    assert all(r["fraction"] <= 1 for r in active)
    assert (
        sum(
            (
                datetime.fromisoformat(r["end_utc"]) - datetime.fromisoformat(r["start_utc"])
            ).total_seconds()
            for r in active
        )
        == 73 * 3600
    )
    new_segments = [r for r in active if r["version"] == version]
    assert len(new_segments) == 96
    assert sum(r["flow"]["charge_wh"] for r in new_segments) == pytest.approx(
        sum(r["flow"]["charge_wh"] for r in new["rows"])
    )


def test_future_or_unsuccessful_plan_never_rewrites_history(source):
    report = dashboard.collect(source, now=NOW)
    before = dashboard.timeline(report["plans"], 7, end=datetime(2026, 10, 30, 12, tzinfo=UTC))
    future = copy.deepcopy(report["plans"][0])
    future["claim_status"] = "uncertain"
    after = dashboard.timeline(
        report["plans"] + [future], 7, end=datetime(2026, 10, 30, 12, tzinfo=UTC)
    )
    assert before == after
    assert all(r.get("version") != future["version"] for r in after)


def test_claim_availability_splits_original_slot_without_multiplying_energy(source):
    report = dashboard.collect(source, now=NOW)
    plan = report["plans"][0]
    plan["claimed_at_utc"] = (
        datetime.fromisoformat(plan["start_utc"]) + timedelta(minutes=5)
    ).isoformat()
    segment = next(r for r in dashboard.timeline([plan], 1) if not r.get("gap"))
    assert segment["fraction"] == pytest.approx(2 / 3)
    assert segment["flow"]["charge_wh"] == pytest.approx(
        plan["rows"][0]["flow"]["charge_wh"] * 2 / 3
    )


@pytest.mark.parametrize(
    "start", [datetime(2026, 3, 29, 0, tzinfo=UTC), datetime(2026, 10, 25, 0, tzinfo=UTC)]
)
def test_dst_keeps_utc_energy_and_distinct_local_offsets(source, start):
    def mutate(s):
        s["start_solution_datetime"] = start.isoformat()
        s["result"]["battery_flow_start_utc"] = start.isoformat()

    path = change_solution(source, mutate)
    version = path.stem[9:]
    state = json.loads((source / "sync-state.json").read_text())
    state["events"][version].update(start_utc=start.isoformat(), claimed_at_utc=start.isoformat())
    state["events"] = {version: state["events"][version]}
    (source / "sync-state.json").write_text(json.dumps(state))
    p = next(p for p in dashboard.collect(source, now=NOW)["plans"] if p["version"] == version)
    assert len({r["start_utc"] for r in p["rows"]}) == 96
    labels = [r["local"] for r in p["rows"]]
    assert any("+0200" in s for s in labels) and any("+0100" in s for s in labels)
    assert sum(r["fraction"] for r in dashboard.timeline([p], 1) if not r.get("gap")) == 96


def test_empty_period_and_initial_empty_state(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "sync.lock").touch()
    (source / "sync-state.json").write_text('{"events":{}}')
    (source / "sync-report.json").write_text('{"event":{"status":"waiting-publication"}}')
    assert dashboard.prepare(dashboard.collect(source, now=NOW))["ranges"] == {
        "1": [],
        "7": [],
        "30": [],
    }


def test_atomic_event_update_and_corrupt_input_retains_last_valid_view(source, tmp_path):
    dest = tmp_path / "dashboard"
    dest.mkdir()
    before = fingerprint(source)
    assert dashboard.refresh(source, dest)
    old = packet(dest / "index.html")
    assert before == fingerprint(source)
    new = event(source)
    assert dashboard.refresh(source, dest)
    valid = packet(dest / "index.html")
    assert len(valid["plans"]) == len(old["plans"]) + 1
    assert valid["plans"][0]["version"] == new
    (source / "sync-state.json").write_text('{"truncated":')
    assert not dashboard.refresh(source, dest)
    error = packet(dest / "index.html")
    assert error["plans"] == valid["plans"] and error["ranges"] == valid["ranges"]
    assert error["checked_at_utc"] == valid["checked_at_utc"]
    assert error["update_error"] is True
    assert not list(dest.glob(".ems-*"))


def test_busy_sync_lock_preserves_last_good_page(source, tmp_path):
    dest = tmp_path / "dashboard"
    dest.mkdir()
    assert dashboard.refresh(source, dest)
    old = packet(dest / "index.html")
    with (source / "sync.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not dashboard.refresh(source, dest)
    assert packet(dest / "index.html")["plans"] == old["plans"]
    assert dashboard.refresh(source, dest)
    assert packet(dest / "index.html")["update_error"] is False


def test_output_lock_skips_duplicate_refresh(source, tmp_path):
    dest = tmp_path / "dashboard"
    dest.mkdir()
    with (dest / ".refresh.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not dashboard.refresh(source, dest)
        assert not (dest / "index.html").exists()


def test_failed_atomic_replace_leaves_complete_previous_html(source, tmp_path, monkeypatch):
    dest = tmp_path / "dashboard"
    dest.mkdir()
    assert dashboard.refresh(source, dest)
    before = (dest / "index.html").read_bytes()
    monkeypatch.setattr(
        dashboard.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError):
        dashboard.refresh(source, dest)
    assert (dest / "index.html").read_bytes() == before
    assert not list(dest.glob(".ems-*"))


@pytest.mark.parametrize("target", ["same", "inside", "ancestor", "symlink_html", "symlink_lock"])
def test_destination_cannot_modify_source_or_follow_symlinks(source, tmp_path, target):
    dest = tmp_path / "dashboard"
    dest.mkdir()
    if target == "same":
        dest = source
    elif target == "inside":
        dest = source / "dashboard"
        dest.mkdir()
    elif target == "ancestor":
        dest = tmp_path
    elif target == "symlink_html":
        (dest / "index.html").symlink_to(source / "sync-state.json")
    else:
        (dest / ".refresh.lock").symlink_to(source / "sync.lock")
    before = fingerprint(source)
    with pytest.raises(ValueError):
        dashboard.refresh(source, dest)
    assert fingerprint(source) == before


def test_symlink_source_lock_rejected_without_opening(source, tmp_path):
    (source / "sync.lock").unlink()
    (source / "sync.lock").symlink_to(tmp_path / "absent")
    with pytest.raises(ValueError):
        dashboard.collect(source)


def test_injection_stays_inert_json_and_no_external_resources(source):
    report = dashboard.prepare(dashboard.collect(source, now=NOW))
    report["test"] = "</script><script>alert(1)</script>"
    html = dashboard_view.render(report)
    assert "</script><script>alert(1)" not in html
    assert json.loads(dashboard.DATA_PATTERN.search(html)[1])["test"] == report["test"]
    assert "script-src 'sha256-" in html
    assert 'src="http' not in html and 'href="http' not in html


def test_standalone_bundle_deterministic_and_runs_isolated_without_installed_modules(
    source, tmp_path
):
    from build_ems_dashboard import build

    raw = build()
    assert raw == build()
    bundle = tmp_path / "ems.pyz"
    bundle.write_bytes(raw)
    dest = tmp_path / "dashboard"
    dest.mkdir()
    run = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(bundle),
            "--source",
            str(source),
            "--destination",
            str(dest),
        ],
        capture_output=True,
    )
    assert run.returncode == 0, run.stderr.decode()
    assert len(packet(dest / "index.html")["plans"]) == 3
    assert "PRIVATE-CANARY" not in (dest / "index.html").read_text()
    assert hashlib.sha256(raw).hexdigest()


def test_history_above_legacy_inspector_64_plan_limit(source):
    for _ in range(64):
        event(source)
    report = dashboard.prepare(dashboard.collect(source, now=NOW))
    assert len(report["plans"]) == 67
    assert report["ranges"]["30"]


def test_old_claimed_files_are_kept_but_do_not_exhaust_active_history(source):
    # Older archives remain in place and need not be parsed to display the last 30 days.
    state = json.loads((source / "sync-state.json").read_text())
    old = "0" * 64
    state["events"][old] = {
        "version": old,
        "status": "succeeded",
        "start_utc": "2025-01-01T00:00:00+00:00",
    }
    (source / f"solution-{old}.json").write_text("deliberately unreadable old fixture")
    (source / "sync-state.json").write_text(json.dumps(state))
    before = fingerprint(source)
    report = dashboard.collect(source, now=NOW)
    assert len(report["plans"]) == 3
    assert fingerprint(source) == before


@pytest.mark.parametrize("seconds", [900, 3600])
def test_stored_energy_is_never_multiplied_by_display_resolution(seconds):
    start = datetime(2026, 10, 30, 12, tzinfo=UTC)
    solution = {
        "result": {
            "battery_flow_energy_basis": "battery_dc",
            "battery_flow_start_utc": start.isoformat(),
            "battery_flow_interval_seconds": seconds,
            "battery_charge_dc_wh_per_hour": [250, 500],
            "battery_discharge_dc_wh_per_hour": [30, 40],
        }
    }
    result = dashboard.flows(solution, 2, start, seconds)
    assert sum(r["charge_wh"] for r in result) == 750
    assert sum(r["discharge_wh"] for r in result) == 70

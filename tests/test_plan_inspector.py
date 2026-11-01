"""All fixture data is synthetic. No API access, simulation or production input."""

import hashlib
import importlib.util
import json
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import build_plan_inspector
import pytest

from eos_pv_helper import plan_inspector as reader
from eos_pv_helper import plan_view

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 29, 13, 5, tzinfo=UTC)
VERSION = "b"*64


def fixture(root, *, seconds=3600, count=24, start=NOW.replace(minute=0), flag=True):
    root.mkdir(exist_ok=True)
    (root / "sync.lock").touch()
    claim = {"version": VERSION, "status": "succeeded", "start_utc": start.isoformat(),
             "claimed_at_utc": (start+timedelta(minutes=5)).isoformat(), "control_hours": 24,
             "effective_tail_hours": 10, "interval_seconds": seconds}
    solution = {"start_solution_datetime": start.isoformat(), "interval_seconds": seconds,
        "controls_start_at_now": flag, "ac_charge": [.5, 0]*((count+1)//2),
        "dc_charge": [1]*count, "discharge_allowed": [0, 1]*((count+1)//2),
        "result": {"total_costs": 2.6875, "total_losses": 2373.7,
                   "battery_soc_per_hour": [55]*count, "costs_per_hour": [.1]*count},
        "terminal_value": {"battery_energy_wh": 9145.8, "credited_euro": .7382}}
    solution["ac_charge"] = solution["ac_charge"][:count]
    solution["discharge_allowed"] = solution["discharge_allowed"][:count]
    values = {"sync-state.json": {"events": {VERSION: claim}},
              "sync-report.json": {"event": {"status": "waiting-publication"}, "errors": {}},
              "solution-"+VERSION+".json": solution,
              # These must NEVER be taken as historical prices/prognoses.
              "prices.json": {"private_live_canary": "DO-NOT-READ"},
              "soc.json": {"private_live_canary": "DO-NOT-READ"},
              "forecast.json": {"private_live_canary": "DO-NOT-READ"}}
    for name, value in values.items():
        (root / name).write_text(json.dumps(value))
    return root, claim, solution


@pytest.fixture
def data(tmp_path):
    return fixture(tmp_path)


def fingerprint(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def test_waiting_keeps_successful_plan_and_all_original_hours(data):
    root, _, _ = data
    before = fingerprint(root)
    report = reader.collect(root, now=NOW)
    plan = report["plans"][0]
    assert report["latest_sync_status"] == "waiting-publication"
    assert report["phase"] == 2 and report["read_only"] is True
    assert plan["claim_status"] == "succeeded" and plan["source_slots"] == 24
    assert len(plan["rows"]) == 24 and sum(len(r["quarters"]) for r in plan["rows"]) == 96
    assert plan["rows"][0]["start_utc"] == "2026-10-29T13:00:00+00:00"
    assert "14:00 CET" in plan["rows"][0]["local"]
    assert plan["summary"]["total_costs"] == 2.6875
    assert plan["inputs"]["status"] == "unproven"
    assert plan["comparison"]["status"] == "not_calculable"
    assert "Nicht berechenbar" in plan["comparison"]["message"]
    assert before == fingerprint(root)


def test_no_implicit_writes_or_network_and_no_live_input_reads(data, monkeypatch):
    root, _, _ = data
    original = Path.open
    def guarded(path, mode="r", *args, **kwargs):
        assert not any(flag in mode for flag in "wax+")
        assert path.name not in {"prices.json", "soc.json", "forecast.json", "config.toml"}
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("Network forbidden"))
    report = reader.collect(root, now=NOW)
    html = plan_view.render(report)
    assert "DO-NOT-READ" not in html
    assert "connect-src 'none'" in html and "default-src 'none'" in html


@pytest.mark.parametrize("seconds,count", [(900, 96), (3600, 24)])
def test_native_and_quarter_resolution_do_not_create_new_decisions(tmp_path, seconds, count):
    root, _, _ = fixture(tmp_path, seconds=seconds, count=count)
    plan = reader.collect(root, now=NOW)["plans"][0]
    assert len(plan["rows"]) == count
    assert sum(len(r["quarters"]) for r in plan["rows"]) == 96
    assert plan["rows"][1]["source_index"] == 1
    assert (reader.stamp(plan["rows"][1]["start_utc"])-reader.stamp(plan["rows"][0]["start_utc"])).total_seconds() == seconds
    assert all("battery_power_w" not in r and "savings" not in r for r in plan["rows"])


@pytest.mark.parametrize("start", [datetime(2026, 3, 29, 0, tzinfo=UTC), datetime(2026, 10, 25, 0, tzinfo=UTC)])
def test_dst_is_a_continuous_utc_axis_with_explicit_local_offsets(tmp_path, start):
    root, _, _ = fixture(tmp_path, seconds=900, count=16, start=start)
    rows = reader.collect(root, now=NOW)["plans"][0]["rows"]
    assert len({r["start_utc"] for r in rows}) == 16
    labels = [r["local"] for r in rows]
    assert any("+0200" in s for s in labels) and any("+0100" in s for s in labels)
    if start.month == 10:
        assert any("02:00 CEST" in s for s in labels) and any("02:00 CET" in s for s in labels)
    else:
        assert not any("02:" in s for s in labels)


@pytest.mark.parametrize("flag", [None, False])
def test_ambiguous_legacy_time_basis_is_not_invented(tmp_path, flag):
    root, _, _ = fixture(tmp_path, flag=flag)
    plan = reader.collect(root)["plans"][0]
    assert plan["time_basis"] == "unproven"
    assert len(plan["rows"]) == 24
    assert all(row["start_utc"] is None and row["quarters"] == [] for row in plan["rows"])
    if flag is False:
        legacy = reader.collect(root, legacy_timezone="Europe/Berlin")["plans"][0]
        assert legacy["rows"][0]["start_utc"] == "2026-10-28T23:00:00+00:00"
        assert legacy["rows"][0]["phase"] == "prefix"


def test_short_arrays_unknown_factors_and_missing_tail_are_visible(data):
    root, _, solution = data
    solution["ac_charge"] = [0, None, 2, "not-a-factor"]
    solution["dc_charge"] = [1]*30
    (root / ("solution-"+VERSION+".json")).write_text(json.dumps(solution))
    plan = reader.collect(root)["plans"][0]
    assert len(plan["rows"]) == 30
    assert plan["rows"][0]["controls"]["ac_charge"] == 0
    assert all(plan["rows"][i]["controls"]["ac_charge"] is None for i in (1, 2, 3, 29))
    assert plan["rows"][24]["phase"] == "tail"
    assert len(plan["rows"]) < 34  # Never append a hypothetical declared tail.


def test_multiple_plans_claims_without_solutions_and_corruption(data):
    root, claim, solution = data
    state = json.loads((root / "sync-state.json").read_text())
    state["events"]["c"*64] = {**claim, "version": "c"*64}
    state["events"]["d"*64] = {**claim, "version": "d"*64}
    (root / "sync-state.json").write_text(json.dumps(state))
    (root / ("solution-"+"c"*64+".json")).write_text(json.dumps(solution))
    (root / ("solution-"+"e"*64+".json")).write_text('{"truncated":')
    report = reader.collect(root)
    assert len(report["plans"]) == 4
    assert sum(p["claim_status"] == "succeeded" for p in report["plans"]) == 3
    assert sum(p["solution_status"] == "unreadable" for p in report["plans"]) == 2


def test_privacy_and_script_injection_never_escape_whitelist(data):
    root, _, solution = data
    secret = 'PRIVATE-TOKEN-192.168.0.123-LOCATION-</script><script>alert(1)</script>'
    solution["parameters"] = {"password": secret, "latitude": 52.5123456, "url": secret}
    solution["comment"] = secret
    solution["ac_charge"][0] = secret
    solution["appliance_starts"] = {secret: [NOW.isoformat()]}
    solution["result"]["electricity_price"] = [secret]
    (root / ("solution-"+VERSION+".json")).write_text(json.dumps(solution))
    report = reader.collect(root)
    html = plan_view.render(report)
    assert secret not in json.dumps(report) and "192.168" not in html and "52.5123456" not in html
    assert "PRIVATE-TOKEN" not in html and "alert(1)" not in html
    assert report["plans"][0]["appliances"][0]["device"] == 1
    dirty = {**report, "warnings": [secret]}
    safe_html = plan_view.render(dirty)
    assert "</script><script>alert(1)" not in safe_html and "\\u003c/script" in safe_html


def test_shared_lock_and_missing_lock_never_repair_or_create_files(data):
    import fcntl
    root, _, _ = data
    before = fingerprint(root)
    with (root / "sync.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        with pytest.raises(reader.InspectorError, match="schreibt gerade"):
            reader.collect(root)
    assert before == fingerprint(root)
    (root / "sync.lock").unlink()
    with pytest.raises(reader.InspectorError, match="kein Lock angelegt"):
        reader.collect(root)
    assert not (root / "sync.lock").exists()


def test_bundle_is_reproducible_and_cli_does_not_need_installed_helper(data, tmp_path):
    root, _, _ = data
    raw = build_plan_inspector.build()
    assert raw == build_plan_inspector.build()
    bundle = tmp_path / "code.pyz"
    bundle.write_bytes(raw)
    before = fingerprint(root)
    result = subprocess.run([sys.executable, "-I", "-S", "-B", str(bundle), "--source", str(root),
        "--format", "json"], capture_output=True)
    assert result.returncode == 0, result.stderr.decode()
    assert json.loads(result.stdout)["plans"][0]["source_slots"] == 24
    assert before == fingerprint(root)


@pytest.mark.parametrize("flag", ["--write-eos", "--refresh-source", "--output"])
def test_mutating_options_are_not_supported(data, tmp_path, flag):
    bundle = tmp_path / "code.pyz"
    bundle.write_bytes(build_plan_inspector.build())
    root = data[0]
    before = fingerprint(root)
    result = subprocess.run([sys.executable, "-I", "-S", "-B", str(bundle), "--source", str(root), flag], capture_output=True)
    assert result.returncode != 0 and not result.stdout
    assert before == fingerprint(root)


def test_only_matching_valid_archive_enables_price_and_pv_overlay(tmp_path, monkeypatch):
    # Real schema-2 synthetic fixture shared with the prior reviewed validator.
    spec = importlib.util.spec_from_file_location("historical_validator", ROOT / "src/eos_pv_helper/historical.py")
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    monkeypatch.setitem(sys.modules, "historical_validator", validator)
    from test_doctor import artifacts, inspect
    base = artifacts.__wrapped__(tmp_path)
    root, _, values = base
    version = next(iter(values["sync-state.json"]["events"]))
    solution = values["solution-"+version+".json"]
    solution["controls_start_at_now"] = True
    start = NOW.replace(hour=0, minute=0)
    pv = {"import_verified": True, "checked_at_utc": NOW.isoformat(), "count": 288,
          "start_utc": start.isoformat(), "end_exclusive_utc": (start+timedelta(hours=72)).isoformat()}
    values["sync-report.json"]["pv"] = pv
    values["sync-report.json"]["prices"]["count"] = 192
    values["sync-report.json"]["prices"]["unit"] = "EUR/Wh"
    inspect(base)
    files = {name: (root / name).read_bytes() for name in values}
    files["soc.json"] = json.dumps(values["sync-report.json"]["soc"]).encode()
    files["report.json"] = json.dumps(pv).encode()
    files["forecast.json"] = json.dumps({"data": {(start+timedelta(minutes=15*i)).isoformat():
        {"pvforecast_ac_power": 1000} for i in range(288)}}).encode()
    manifest = {"schema_version": 2, "event_version": version, "captured_at_utc": NOW.isoformat(),
        "timezone": "Europe/Berlin", "configured_constraints_read": True,
        "validation_constraints": {"max_age_seconds": 300, "max_abs_power_w": 20000},
        "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
    directory = root / "genetic-evidence"
    directory.mkdir()
    path = directory / (version+".zip")
    path.write_bytes(validator.pack(manifest, files))
    plan = reader.collect(root, now=NOW)["plans"][0]
    assert plan["inputs"]["status"] == "verified"
    assert plan["rows"][0]["quarters"][0]["price_eur_kwh"] == .3
    assert plan["rows"][0]["quarters"][0]["pv_w"] == 1000
    (root / ("solution-"+version+".json")).write_bytes(files["solution-"+version+".json"]+b" ")
    assert reader.collect(root, now=NOW)["plans"][0]["inputs"]["status"] == "unproven"


def test_all_known_control_fields_tail_and_appliance_decisions_are_preserved(data):
    root, _, solution = data
    solution.update(battery_grid_export_allowed=[0, 1], battery_grid_export_factor=[0, .25],
                    ev_charge_hours_float=[0, .5],
                    ev_obj={"device_id": "SECRET-IP-192.168.0.7", "charge_array": [0, .5], "discharge_array": [1, 0]},
                    appliance_starts={"private-device": [NOW.isoformat()]},
                    appliance_deadline_missed={"private-device": True})
    solution["result"]["home_appliance_running"] = {"private-device": [True, False]}
    solution["terminal_value"]["tail_plan"] = [{"hour_from_start": 24, "ac_charge_factor": .4,
        "dc_charge_allowed": 1, "discharge_allowed": 0, "battery_grid_export_factor": 0,
        "soc_start_percentage": 60, "soc_end_percentage": 70}]
    (root / ("solution-"+VERSION+".json")).write_text(json.dumps(solution))
    plan = reader.collect(root)["plans"][0]
    assert set(plan["controls"]) == set(reader.CONTROL_FIELDS)
    assert plan["rows"][1]["controls"]["battery_grid_export_factor"] == .25
    assert plan["tail"][0]["start_utc"] == "2026-10-30T13:00:00+00:00"
    assert plan["appliance_running"][0]["values"] == [True, False]
    assert plan["unmapped_ev_arrays"]["ev_obj.charge_array"] == [0, .5]
    assert "private-device" not in json.dumps(plan) and "SECRET-IP" not in json.dumps(plan)


def test_missing_claim_does_not_hide_existing_control_arrays(data):
    root, _, _ = data
    (root / "sync-state.json").write_text('{"events":{}}')
    plan = reader.collect(root)["plans"][0]
    assert plan["claim_status"] == "unmatched" and len(plan["rows"]) == 24
    assert plan["inputs"]["status"] == "unproven"


def test_symlink_solution_is_not_followed(data):
    root, _, _ = data
    path = root / ("solution-"+VERSION+".json")
    path.unlink()
    path.symlink_to(root / "prices.json")
    plan = reader.collect(root)["plans"][0]
    assert plan["claim_status"] == "succeeded" and plan["solution_status"] == "unreadable" and plan["rows"] == []


def test_anonymized_device_numbers_do_not_link_different_devices(data):
    root, _, solution = data
    solution["appliance_starts"] = {"z-private": [NOW.isoformat()]}
    solution["result"]["home_appliance_running"] = {"a-private": [True, False]}
    (root / ("solution-"+VERSION+".json")).write_text(json.dumps(solution))
    plan = reader.collect(root)["plans"][0]
    assert plan["appliances"][0]["device"] == 2
    assert plan["appliance_running"][0]["device"] == 1


def test_mismatched_claim_does_not_supply_horizon_or_historical_inputs(data):
    root, claim, _ = data
    claim["start_utc"] = "2026-10-28T13:00:00+00:00"
    (root / "sync-state.json").write_text(json.dumps({"events": {VERSION: claim}}))
    plan = reader.collect(root)["plans"][0]
    assert plan["claim_status"] == "succeeded"  # Actual record status is preserved.
    assert plan["source_slots"] == 24 and plan["control_hours"] is None
    assert all(r["phase"] == "undeclared" for r in plan["rows"])
    assert plan["inputs"]["status"] == "unproven"

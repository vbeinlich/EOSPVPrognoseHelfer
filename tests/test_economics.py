"""Synthetic benchmarks; no private forecasts or optimizer calls."""

import copy
import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from eos_pv_helper import economics as cost
from eos_pv_helper import economics_report, plan_inspector, plan_view


def saved(*, count=24, seconds=3600):
    """Hand-calculable zero-PV hold plan, unity efficiencies, 40% initial SoC."""
    start = "2026-10-31T12:00:00+00:00"
    loads = [1000*seconds/3600]*count
    prices = [.0003]*count
    capacity = 13000
    return {"start_solution_datetime": start, "controls_start_at_now": True,
        "interval_seconds": seconds, "ac_charge": [0]*count, "dc_charge": [1]*count,
        "discharge_allowed": [0]*count,
        "parameters": {"forecast_interval_seconds": seconds,
            "ems": {"pv_forecast_wh": [0]*count, "total_load": loads,
                    "electricity_price_per_wh": prices, "feed_in_tariff_per_wh": [.000072]*count},
            "pv_battery": {"device_id": "PRIVATE-DEVICE-192.168.1.1", "capacity_wh": capacity,
                "initial_soc_percentage": 40, "min_soc_percentage": 10, "max_soc_percentage": 100,
                "charging_efficiency": 1, "discharging_efficiency": 1, "max_charge_power_w": 6000,
                "levelized_cost_of_storage_kwh": 0},
            "inverter": {"device_id": "PRIVATE-INVERTER", "battery_id": "PRIVATE-DEVICE-192.168.1.1",
                "max_power_wh": 12000, "ac_to_dc_efficiency": 1, "dc_to_ac_efficiency": 1,
                "max_ac_charge_power_w": 6000, "ac_charge_limits_total_charge": False,
                "dc_to_ac_efficiency_curve": None, "dc_to_ac_efficiency_reference_load_fraction": .06}},
        "result": {"grid_consumption_wh_per_hour": loads, "grid_feed_in_wh_per_hour": [0]*count,
            "battery_soc_per_hour": [40]*count, "costs_per_hour": [v*.0003 for v in loads],
            "revenue_per_hour": [0]*count, "losses_per_hour": [0]*count,
            "electricity_price": prices.copy(), "feed_in_tariff": [.000072]*count,
            "total_costs": sum(loads)*.0003, "total_revenue": 0, "total_balance": sum(loads)*.0003,
            "total_losses": 0},
        "terminal_value": {"mode": "AUTO", "control_horizon_hours": count*seconds/3600,
            "battery_energy_wh": 3900, "credited_euro": 1.17,
            "curve": {"energy_wh": [0, 11700], "value_euro": [0, 3.51]}}}


@pytest.mark.parametrize("path", [
    ("parameters", "ems", "total_load"), ("parameters", "ems", "pv_forecast_wh"),
    ("parameters", "ems", "electricity_price_per_wh"), ("parameters", "pv_battery", "initial_soc_percentage"),
    ("parameters", "pv_battery", "charging_efficiency"), ("parameters", "inverter", "dc_to_ac_efficiency"),
    ("terminal_value", "curve"), ("result", "battery_soc_per_hour")])
def test_missing_original_data_is_explicitly_not_calculable(path):
    original = saved()
    node = original
    for key in path[:-1]:
        node = node[key]
    node.pop(path[-1])
    result = cost.evaluate(original)
    assert result["status"] == "not_calculable" and result["message"].startswith("Nicht berechenbar")
    assert "additional_savings_eur" not in result


@pytest.mark.parametrize("change", ["alias", "price", "length", "nan", "interval", "timezone", "curve", "device", "ev", "export", "legacy"])
def test_inconsistent_cycles_and_unsupported_models_fail_closed(change):
    s = saved()
    if change == "alias":
        s["parameters"]["ems"]["gesamtlast"] = [2]*24
    elif change == "price":
        s["result"]["electricity_price"][0] = .99
    elif change == "length":
        s["parameters"]["ems"]["total_load"].pop()
    elif change == "nan":
        s["parameters"]["ems"]["pv_forecast_wh"][0] = float("nan")
    elif change == "interval":
        s["parameters"]["forecast_interval_seconds"] = 900
    elif change == "timezone":
        s["start_solution_datetime"] = "2026-10-31T13:00:00"
    elif change == "curve":
        s["terminal_value"]["curve"]["energy_wh"] = [0, 100]
    elif change == "device":
        s["parameters"]["inverter"]["battery_id"] = "other"
    elif change == "ev":
        s["parameters"]["ev"] = {"capacity_wh": 50000}
    elif change == "export":
        s["battery_grid_export_factor"] = [1]*24
    elif change == "legacy":
        s["controls_start_at_now"] = False
    assert cost.evaluate(s)["status"] == "not_calculable"


def test_numeric_projection_has_no_secrets_and_round_trips_exactly():
    s = saved()
    s["parameters"]["token"] = "PRIVATE-TOKEN"
    s["parameters"]["pv_battery"]["password"] = "PRIVATE-PASSWORD"
    s["secret"] = "</script><script>bad()</script>"
    p = cost.project(s)
    assert "PRIVATE" not in json.dumps(p) and "192.168" not in json.dumps(p)
    assert cost.project(cost.as_solution(p)) == p


def test_cost_components_losses_and_terminal_credit_are_counted_once():
    run = {"slots": [{"grid_cost_eur": 2, "feed_in_revenue_eur": .4, "wear_eur": .1,
            "grid_import_wh": 5000, "grid_export_wh": 1000, "losses_wh": 800}],
           "end_soc_percent": 50, "end_usable_ac_wh": 2000}
    r = cost.account(run, {"energy_wh": [0, 10000], "value_euro": [-2, 1]})
    assert r["operating_cost_eur"] == pytest.approx(1.7)
    assert r["terminal_credit_eur"] == pytest.approx(-1.4)
    assert r["adjusted_cost_eur"] == pytest.approx(3.1)
    assert r["losses_kwh"] == .8  # No fictitious extra 0.8 kWh * price expense.


def test_curve_is_identical_for_both_scenarios_and_no_extrapolation():
    curve = {"energy_wh": [0, 1000, 5000], "value_euro": [-1, 0, 1]}
    assert cost.terminal_value(curve, 500) == -.5
    assert cost.terminal_value(curve, 3000) == .5
    with pytest.raises(cost.ComparisonError, match="außerhalb"):
        cost.terminal_value(curve, 5001)


def test_waiting_export_does_not_open_live_inputs_or_modify_files(tmp_path, monkeypatch):
    s = saved()
    version = "a"*64
    (tmp_path/"sync.lock").touch()
    (tmp_path/"sync-state.json").write_text(json.dumps({"events": {version: {"version": version,
        "status": "succeeded", "interval_seconds": 3600, "control_hours": 24,
        "start_utc": s["start_solution_datetime"]}}}))
    (tmp_path/"sync-report.json").write_text('{"event":{"status":"waiting-publication"}}')
    (tmp_path/("solution-"+version+".json")).write_text(json.dumps(s))
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    original = type(tmp_path).open
    def read_only(path, mode="r", *a, **kw):
        assert not any(c in mode for c in "wax+")
        assert path.name not in ("prices.json", "forecast.json", "soc.json", "config.toml")
        return original(path, mode, *a, **kw)
    monkeypatch.setattr(type(tmp_path), "open", read_only)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    # No native imports/config initialization in this pure reader test.
    monkeypatch.setattr(cost, "evaluate", lambda *a, **k: pytest.fail("NAS reader must never invoke the native engine"))
    packet = plan_inspector.collect(tmp_path, replay_inputs=True)
    assert packet["latest_sync_status"] == "waiting-publication"
    assert packet["plans"][0]["replay_inputs"]["projection"]
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    assert "PRIVATE" not in json.dumps(packet)


def packet():
    projection = cost.project(saved())
    return {"schema_version": 1, "read_only": True, "latest_sync_status": "waiting-publication",
        "plans": [{"version": "a"*64, "claim_status": "succeeded", "start_utc": projection["start_utc"],
            "interval_seconds": 3600, "control_hours": 24, "solution_sha256": "b"*64,
            "replay_inputs": {"schema_version": 1, "source_sha256": "b"*64,
                "projection_sha256": cost.digest(projection), "projection": projection}}]}


def test_offline_packet_hash_failures_are_not_calculable_and_free_text_not_rendered():
    p = packet()
    p["plans"][0]["replay_inputs"]["projection"]["series"]["total_load"][0] += 1
    p["warnings"] = ["PRIVATE-192.168.0.1-</script>"]
    p["plans"][0]["message"] = "PRIVATE-192.168.0.1"
    r = economics_report.from_packet(p)
    assert r["plans"][0]["comparison"]["status"] == "not_calculable"
    assert "PRIVATE" not in plan_view.render(r)


def test_missing_packet_projection_remains_visible_not_a_fake_zero_saving():
    p = packet()
    p["plans"][0]["replay_inputs"] = None
    r = economics_report.from_packet(p)
    assert len(r["plans"]) == 1
    assert r["plans"][0]["comparison"]["message"].startswith("Nicht berechenbar")
    assert "additional_savings_eur" not in r["plans"][0]["comparison"]


def test_mismatched_claim_does_not_replay_or_produce_savings(monkeypatch):
    p = packet()
    p["plans"][0]["control_hours"] = 48
    monkeypatch.setattr(cost, "evaluate", lambda *a, **k: pytest.fail("Mismatched claim must not be simulated"))
    r = economics_report.from_packet(p)
    c = r["plans"][0]["comparison"]
    assert c["status"] == "not_calculable" and "Claim" in c["message"]


def test_projection_is_deterministic_and_does_not_change_original():
    s = saved()
    before = copy.deepcopy(s)
    assert cost.digest(cost.project(s)) == cost.digest(cost.project(s))
    assert s == before


def test_old_container_numeric_fixture_has_complete_original_slots():
    original = json.loads((Path(__file__).parent/"fixtures/economics-hold.json").read_text())
    p = cost.project(original)
    assert p["control_slots"] == 24 and sum(p["series"]["total_load"]) == 24000


def test_cli_missing_original_is_a_not_calculable_row_not_an_aborted_batch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["economics-report", "--solution", str(tmp_path/"missing.json")])
    assert economics_report.main() == 2
    output = json.loads(capsys.readouterr().out)
    assert output["plans"][0]["comparison"]["status"] == "not_calculable"
    assert output["plans"][0]["source_solution_sha256"] is None


@pytest.mark.parametrize("start", ["2026-03-29T00:00:00+00:00", "2026-10-25T00:00:00+00:00"])
def test_projection_preserves_dst_utc_grid(start):
    s = saved(count=96, seconds=900)
    s["start_solution_datetime"] = start
    p = cost.project(s)
    assert p["interval_seconds"] == 900 and p["control_slots"] == 96
    assert datetime.fromisoformat(p["start_utc"]).tzinfo == UTC

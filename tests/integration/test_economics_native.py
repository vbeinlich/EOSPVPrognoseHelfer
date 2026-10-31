"""Real pinned EOS forward simulations; never optimize_ems, HTTP or device IO."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from test_economics import packet, saved  # noqa: E402

from eos_pv_helper import economics as cost  # noqa: E402
from eos_pv_helper import economics_native as native  # noqa: E402
from eos_pv_helper import economics_report  # noqa: E402


@pytest.fixture(autouse=True)
def forbid_optimizer_and_http(monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from requests.sessions import Session

    def forbidden(*a, **kw):
        pytest.fail("Forward comparison must never call an optimizer or HTTP")
    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)


def test_hand_calculated_hold_vs_self_consumption_and_end_soc_fairness():
    result = cost.evaluate(saved())
    assert result["status"] == "calculated", result
    b, g = result["baseline"], result["genetic"]
    assert g["grid_kwh"] == 24
    assert b["grid_kwh"] == pytest.approx(20.1)
    assert g["end_soc_percent"] == 40 and b["end_soc_percent"] == 10
    assert g["operating_cost_eur"] == pytest.approx(7.2)
    assert b["operating_cost_eur"] == pytest.approx(6.03)
    assert g["terminal_credit_eur"] == pytest.approx(1.17)
    assert result["additional_savings_eur"] == pytest.approx(0, abs=1e-9)


def test_losses_and_wear_follow_delivered_dc_energy_once():
    s = saved(count=2)
    s["parameters"]["pv_battery"].update(initial_soc_percentage=0, min_soc_percentage=0,
        charging_efficiency=.9, discharging_efficiency=.9, max_charge_power_w=1000,
        levelized_cost_of_storage_kwh=.04)
    s["parameters"]["inverter"].update(ac_to_dc_efficiency=.8, dc_to_ac_efficiency=.8,
        max_ac_charge_power_w=1000)
    s["parameters"]["ems"]["total_load"] = [0, 1000]
    s["ac_charge"] = [1, 0]
    s["discharge_allowed"] = [0, 1]
    # Project before changing only to obtain the whitelist; populate correct curve domain.
    s["terminal_value"]["curve"] = {"energy_wh": [0, 9360], "value_euro": [0, 2.808]}
    p = cost.project(s)
    r = native.simulate(p, baseline=False, load_scale=1)
    assert r["slots"][0]["grid_import_wh"] == pytest.approx(1000)
    assert r["slots"][1]["grid_import_wh"] == pytest.approx(1000-1000*.8*.9*.9*.8)
    assert sum(x["wear_eur"] for x in r["slots"]) == pytest.approx(1000*.8*.9*.9*.04/1000)
    assert sum(x["losses_wh"] for x in r["slots"]) == pytest.approx(1000*(1-.8*.9*.9*.8))


def test_pv_surplus_reference_charges_and_no_grid_charge():
    s = saved(count=2)
    s["parameters"]["ems"].update(pv_forecast_wh=[2000, 0], total_load=[0, 1000])
    p = cost.project(s)
    r = native.simulate(p, baseline=True, load_scale=1)
    assert [x["grid_import_wh"] for x in r["slots"]] == [0, 0]
    assert r["end_soc_percent"] == pytest.approx(40+1000/13000*100)


def test_native_replay_mismatch_blocks_any_savings():
    s = saved()
    s["result"]["total_costs"] += .1
    r = cost.evaluate(s)
    assert r["status"] == "not_calculable" and "weichen" in r["message"]
    assert "additional_savings_eur" not in r


def test_negative_prices_negative_saving_and_percent_not_invented():
    s = saved()
    s["parameters"]["ems"]["electricity_price_per_wh"] = [-.0001]*24
    s["result"].update(electricity_price=[-.0001]*24, costs_per_hour=[-.1]*24,
                       total_costs=-2.4, total_balance=-2.4)
    r = cost.evaluate(s)
    assert r["status"] == "calculated"
    assert r["additional_savings_percent"] is None


def test_load_sensitivity_is_explicit_fixed_controls_not_a_new_optimized_plan():
    s = saved()
    before = copy.deepcopy(s)
    r = cost.evaluate(s, scaled_load=True)
    assert r["status"] == "calculated"
    scenario = r["sensitivity"]
    assert scenario["method"] == "linear_scaled_saved_load_fixed_controls_and_terminal_curve"
    assert scenario["load_scale"] == 11251/8000
    assert scenario["annual_configuration_verified"] is False and scenario["reoptimized_plan"] is False
    assert sum(x["load_wh"] for x in scenario["slots"]["genetic"]) == pytest.approx(24000*11251/8000)
    assert s == before


def test_hour_and_quarter_hour_equal_energy_cost_and_end_soc():
    hourly = cost.evaluate(saved())
    quarters = cost.evaluate(saved(count=96, seconds=900))
    for name in ("baseline", "genetic"):
        for key in ("operating_cost_eur", "adjusted_cost_eur", "end_soc_percent", "grid_kwh"):
            assert hourly[name][key] == pytest.approx(quarters[name][key])


def test_offline_packet_replay_has_same_comparison_no_current_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = economics_report.from_packet(packet(), scaled_load=True)
    c = result["plans"][0]["comparison"]
    assert c["status"] == "calculated"
    assert c["source_solution_sha256"] == "b"*64
    assert c["additional_savings_eur"] == pytest.approx(0, abs=1e-9)
    assert not list(tmp_path.iterdir())
    assert "PRIVATE" not in json.dumps(result)


def test_engine_fingerprint_rejects_unknown_source(tmp_path):
    for name in native.EXPECTED_SOURCE:
        target = tmp_path/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"not the reviewed EOS source")
    with pytest.raises(cost.ComparisonError, match="ungeprüft"):
        native.fingerprint(tmp_path)


def test_smoke_stdout_needs_no_writable_host_artifact_mount(tmp_path):
    script = Path(__file__).resolve().parents[2]/"scripts/economics_smoke.py"
    result = subprocess.run([sys.executable, "-B", str(script), "--html", "-"],
                            cwd=tmp_path, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout.startswith(b"<!doctype html>")
    assert b'"native_replay_verified": true' in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("reverse", [False, True])
def test_known_price_shift_saving_and_loss_are_both_reported(reverse):
    s = saved(count=2)
    prices = [.0005, .0001] if reverse else [.0001, .0005]
    s["parameters"]["pv_battery"].update(capacity_wh=10000, initial_soc_percentage=10, min_soc_percentage=0)
    s["parameters"]["ems"]["electricity_price_per_wh"] = prices
    s["discharge_allowed"] = [0, 1]
    s["result"].update(grid_consumption_wh_per_hour=[1000, 0], battery_soc_per_hour=[10, 10],
        costs_per_hour=[prices[0]*1000, 0], electricity_price=prices.copy(),
        total_costs=prices[0]*1000, total_balance=prices[0]*1000)
    s["terminal_value"].update(battery_energy_wh=0, credited_euro=0,
        curve={"energy_wh": [0, 10000], "value_euro": [0, 3]})
    result = cost.evaluate(s)
    assert result["status"] == "calculated", result
    assert result["additional_savings_eur"] == pytest.approx(-.4 if reverse else .4)
    assert result["baseline"]["end_soc_percent"] == result["genetic"]["end_soc_percent"] == 0

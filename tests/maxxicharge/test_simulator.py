import copy
import math
import random
import socket
from datetime import UTC, datetime

import pytest
from maxxicharge_fixture import make

from ems_maxxicharge.adapter import Intent, SimulationAdapter, journal
from ems_maxxicharge.battery import Battery
from ems_maxxicharge.config import BatteryConfig, Config, Panel, SimulationError
from ems_maxxicharge.engine import simulate
from ems_maxxicharge.inputs import canonical, from_actuals, from_eos, read_json, validate
from ems_maxxicharge.pv import generate, poa, sun_position


def empty_case(prices=(0.1, 0.5, 0.5, 0.5)):
    data = make(days=1)
    data["rows"] = data["rows"][:len(prices)]
    data["e3dc"]["initial_soc_percent"] = 10
    for row, price in zip(data["rows"], prices):
        row.update(load_wh=200, base_pv_wh=0, import_eur_kwh=price)
        row["weather"].update(ghi=0, dni=0, dhi=0, solar_elevation_deg=-10)
    return data


def test_analytical_efficiency_and_reserve():
    b = Battery(BatteryConfig())
    assert b.energy == 500
    assert b.charge(1000, 1, "extra_pv") == 1000
    f = b.finish(1)
    assert f["end_wh"] == 1420
    assert f["losses_wh"] == pytest.approx(80)
    b.begin()
    assert b.discharge(1000, 1) == 800
    f = b.finish(1)
    assert f["end_wh"] == pytest.approx(1420 - 800 / .92)
    assert f["output_by_source_wh"]["extra_pv"] == pytest.approx(800)
    b.begin()
    assert b.discharge(1000, 1) == pytest.approx((1420 - 800 / .92 - 500) * .92)
    assert b.finish(1)["soc_percent"] == pytest.approx(10)


def test_full_cycle_has_no_free_energy():
    b = Battery(BatteryConfig())
    accepted = b.charge(20000, 10, "grid")
    assert accepted == pytest.approx(4500 / .92)
    b.finish(10)
    b.begin()
    output = b.discharge(20000, 10)
    assert output == pytest.approx(4500 * .92)
    assert output / accepted == pytest.approx(.92 ** 2)
    assert b.finish(10)["soc_percent"] == pytest.approx(10)


@pytest.mark.parametrize("demand,expected", [(0, 0), (50, 50), (1000, 200)])
def test_variable_discharge_and_quarter_hour_limit(demand, expected):
    b = Battery(BatteryConfig(initial_soc_percent=100))
    assert b.discharge(demand, .25) == expected
    assert b.finish(.25)["discharge_w"] == expected * 4


def test_source_pools_and_no_simultaneous_charge_discharge():
    b = Battery(BatteryConfig())
    b.charge(500, 1, "extra_pv")
    b.charge(500, 1, "grid")
    with pytest.raises(SimulationError):
        b.discharge(1, 1)
    b.finish(1)
    b.begin()
    b.discharge(800, 1)
    f = b.finish(1)
    assert f["output_by_source_wh"]["grid"] == pytest.approx(400)
    assert f["output_by_source_wh"]["extra_pv"] == pytest.approx(400)
    with pytest.raises(SimulationError):
        b.charge(1, 1, "base_pv")


@pytest.mark.parametrize("prices,charges", [((.1, .5, .5, .5), True),
    ((.1, .11, .11, .11), False), ((.3, .3, .3, .3), False),
    ((-.1, .4, .4, .4), True), ((.1, .05, .5, .5), False),
    ((.1, .1, .5, .5), True)])
def test_price_spread_and_future_cheaper_opportunity(prices, charges):
    report = simulate(empty_case(prices), Config())
    rows = report["scenarios"]["pv2_bat5"]["rows"]
    assert (rows[0]["maxxi"]["charge_grid_wh"] > 0) is charges
    if charges:
        assert rows[0]["e3dc"]["discharge_wh"] == 0
        assert rows[0]["maxxi"]["discharge_wh"] == 0
    assert report["scenarios"]["pv2_bat5"]["summary"]["savings_cash_eur"] >= -1e-9


def test_no_grid_charge_when_disabled_or_no_future_load():
    report = simulate(empty_case(), Config(grid_charging_enabled=False))
    assert all(r["maxxi"]["charge_grid_wh"] == 0
               for r in report["scenarios"]["pv2_bat5"]["rows"])
    data = empty_case()
    for row in data["rows"][1:]:
        row["load_wh"] = 0
    report = simulate(data, Config())
    assert report["scenarios"]["pv2_bat5"]["rows"][0]["maxxi"]["charge_grid_wh"] == 0


def test_maxxi_own_pv_charges_first_and_e3dc_covers_remaining_demand():
    data = empty_case((.3, .3))
    data["pv_source"] = {"mode": "cached_planes"}
    for index, row in enumerate(data["rows"]):
        row.update(base_pv_wh=200 if index == 0 else 0, load_wh=100 if index == 0 else 400)
        row["planes"] = {name: {"basis": "ac_equivalent_front_wh_per_kwp", "wh_per_kwp":
            100 if index == 0 else 0, "tilt_deg": tilt, "azimuth_deg": 180}
            for name, tilt in (("suedhuette", 14), ("suedzaun", 90))}
    report = simulate(data, Config(grid_charging_enabled=False))
    first, second = report["scenarios"]["pv2_bat5"]["rows"]
    assert first["maxxi"]["charge_pv_wh"] == 200
    assert first["e3dc"]["charge_pv_wh"] == 100
    assert second["maxxi"]["discharge_wh"] == pytest.approx(200 * .92 ** 2)
    assert second["e3dc"]["discharge_wh"] == pytest.approx(100 * .92 ** 2)
    assert all(r["battery_transfer_wh"] == 0 for r in (first, second))


def test_terminal_value_accounts_for_initial_inventory_and_investment():
    data = empty_case((.3,))
    cfg = Config(maxxi=BatteryConfig(initial_soc_percent=100),
                 investments_eur={"pv2_bat5": 2000})
    r = simulate(data, cfg)["scenarios"]["pv2_bat5"]["summary"]
    assert r["initial_usable_ac_wh"] == pytest.approx(4500 * .92)
    assert r["inventory_change_value_eur"] < 0
    assert r["savings_inventory_adjusted_eur"] < r["savings_cash_eur"]
    assert r["investment_eur"] == 2000
    assert r["horizon_savings_minus_investment_eur"] == pytest.approx(r["savings_cash_eur"] - 2000)
    assert r["annualized_savings_eur"] is None
    assert r["payback_years"] is None


def test_short_forecasts_cannot_be_annualized():
    with pytest.raises(SimulationError):
        simulate(make(), Config(representative_year_confirmed=True))


@pytest.mark.parametrize("seed", range(8))
def test_randomized_multiday_energy_conservation_and_mutual_exclusions(seed):
    rng = random.Random(seed)
    data = make(days=5)
    for row in data["rows"]:
        row["load_wh"] = rng.uniform(0, 3000)
        row["base_pv_wh"] *= rng.uniform(0, 1.5)
        row["import_eur_kwh"] = rng.uniform(-.2, .6)
    before = canonical(data)
    report = simulate(data, Config())
    assert canonical(data) == before
    for scenario in report["scenarios"].values():
        assert abs(scenario["summary"]["balance_error_wh"]) < 1e-6
        for row in scenario["rows"]:
            assert abs(row["balance_error_wh"]) < 1e-6
            assert min(row["grid_import_wh"], row["grid_export_wh"]) < 1e-7
            states = [b for b in (row["maxxi"], row["e3dc"]) if b]
            # Independently calculate the physical balance; do not just trust the
            # producer's balance_error_wh diagnostic.
            assert row["pv_wh"] + row["grid_import_wh"] + sum(b["start_wh"] for b in states) == pytest.approx(
                row["load_wh"] + row["grid_export_wh"] + row["losses_wh"]
                + sum(b["end_wh"] for b in states), abs=1e-6)
            for state in states:
                assert 10 - 1e-7 <= state["soc_percent"] <= 100 + 1e-7
                assert min(state["charge_pv_wh"] + state["charge_grid_wh"],
                           state["discharge_wh"]) < 1e-7
                assert abs(state["balance_error_wh"]) < 1e-6
                assert state["start_wh"] + state["charge_pv_wh"] + state["charge_grid_wh"] == pytest.approx(
                    state["end_wh"] + state["discharge_wh"] + state["losses_wh"], abs=1e-6)
            if any(b["charge_grid_wh"] > 1e-7 for b in states):
                assert sum(b["discharge_wh"] for b in states) == 0
            assert row["maxxi"] is None or row["maxxi"]["discharge_w"] <= 800 + 1e-7


@pytest.mark.parametrize("key,value", [("load_wh", -1), ("load_wh", True),
    ("base_pv_wh", float("nan")), ("import_eur_kwh", float("inf")), ("export_eur_kwh", None)])
def test_invalid_input_values_block(key, value):
    data = empty_case()
    data["rows"][0][key] = value
    with pytest.raises(SimulationError):
        simulate(data, Config())


@pytest.mark.parametrize("mutation", ["gap", "duplicate", "overlap", "timezone", "scope", "hash"])
def test_incomplete_or_ambiguous_inputs_block(mutation):
    data = empty_case()
    if mutation == "gap":
        del data["rows"][1]
    elif mutation in ("duplicate", "overlap"):
        data["rows"][1]["start_utc"] = data["rows"][0]["start_utc"]
    elif mutation == "timezone":
        data["rows"][0]["start_utc"] = "2026-06-18T00:00:00"
    elif mutation == "scope":
        data["load_scope"] = "unknown"
    else:
        data["source_sha256"] = []
    with pytest.raises(SimulationError):
        validate(data)


def test_dst_offsets_are_normalized_without_duplicate_local_hour():
    data = empty_case((.3, .3))
    data["rows"][0].update(start_utc="2026-10-25T02:45:00+02:00",
                            end_utc="2026-10-25T02:00:00+01:00")
    data["rows"][1].update(start_utc="2026-10-25T02:00:00+01:00",
                            end_utc="2026-10-25T02:15:00+01:00")
    rows, _ = validate(data)
    assert all(r["interval_seconds"] == 900 for r in rows)


def test_geometry_and_bifacial_yield_analytical():
    assert poa(1000, 1000, 0, 90, 180, 0, 180, .2) == pytest.approx(1000)
    assert poa(500, 1000, 0, 30, 180, 90, 180, 0) == pytest.approx(math.sqrt(3) * 500)
    assert poa(1000, 1000, 1000, -1, 180, 14, 180, .2) == 0
    data = make(days=1)
    rows, _ = validate(data)
    a, _ = generate(rows, data["pv_source"], Config())
    cfg = Config(panels=(Panel("suedhuette", bifacial_gain=.1),
                         Panel("suedzaun", tilt_deg=90, bifacial_gain=.2)))
    b, _ = generate(rows, data["pv_source"], cfg)
    assert sum(b["suedhuette"]) == pytest.approx(sum(a["suedhuette"]) * 1.1)
    assert sum(b["suedzaun"]) == pytest.approx(sum(a["suedzaun"]) * 1.2)
    assert a["suedhuette"] != a["suedzaun"]


def test_approximate_solar_position_sanity():
    elevation, _ = sun_position(datetime(2026, 3, 20, 12, tzinfo=UTC), 0, 0)
    assert elevation > 87
    elevation, _ = sun_position(datetime(2026, 3, 20, 0, tzinfo=UTC), 0, 0)
    assert elevation < -87


def test_proxy_needs_acknowledgement_and_wrong_plane_geometry_blocks():
    data = empty_case()
    data["pv_source"] = {"mode": "reference_proxy"}
    with pytest.raises(SimulationError):
        simulate(data, Config())
    data["pv_source"] = {"mode": "cached_planes"}
    for row in data["rows"]:
        row["planes"] = {}
    with pytest.raises(SimulationError):
        simulate(data, Config())


def test_all_four_scenarios_identical_input_deterministic_and_no_network(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("No network permitted"))
    data = make()
    a = simulate(data, Config())
    b = simulate(data, Config())
    assert canonical(a) == canonical(b)
    assert set(a["scenarios"]) == {"e3dc", "pv2_bat5", "pv6_bat10", "pv6_only"}
    for row2, row6 in zip(a["scenarios"]["pv2_bat5"]["rows"],
                          a["scenarios"]["pv6_only"]["rows"]):
        assert row6["extra_pv_wh"] == pytest.approx(row2["extra_pv_wh"] * 3)
    assert a["scenarios"]["pv6_only"]["maxxi_config"] is None
    assert a["scenarios"]["pv6_bat10"]["maxxi_config"]["capacity_wh"] == 10000
    messages = list(journal(a))
    assert len(messages) == 4 * len(data["rows"])
    assert all(m["topic"].startswith("ems/sim/maxxicharge/v1/")
               and m["payload"]["mode"] == "SIM" and m["retain"] is False
               and m["transport"] == "local_journal_only" for m in messages)


@pytest.mark.parametrize("d,g,end", [(801, 0, "00:15"), (0, 801, "00:15"),
    (1, 1, "00:15"), (0, 0, "00:00")])
def test_adapter_rejects_unsafe_intents(d, g, end):
    adapter = SimulationAdapter("a" * 64, "pv2_bat5")
    with pytest.raises(SimulationError):
        adapter.apply_intent(Intent("1", "2026-06-18T00:00:00Z",
                                   "2026-06-18T" + end + ":00Z", d, g))


def test_duplicate_json_keys_fail(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"a":1,"a":2}')
    with pytest.raises(SimulationError):
        read_json(path)


def eos_case():
    return {"controls_start_at_now": True, "interval_seconds": 900,
            "start_solution_datetime": "2026-06-18T00:00:00Z", "ac_charge": [0, 0],
            "parameters": {"forecast_interval_seconds": 900,
                "ems": {"total_load": [200, 200], "pv_forecast_wh": [0, 0],
                        "electricity_price_per_wh": [.0001, .0004],
                        "feed_in_tariff_per_wh": [.00008, .00008]},
                "pv_battery": {"capacity_wh": 13000, "initial_soc_percentage": 10,
                    "min_soc_percentage": 10, "max_soc_percentage": 100,
                    "charging_efficiency": .95, "discharging_efficiency": .96,
                    "max_charge_power_w": 6000},
                "inverter": {"ac_to_dc_efficiency": .97, "dc_to_ac_efficiency": .98,
                    "max_power_wh": 6000, "dc_to_ac_efficiency_curve": None}}}


def test_eos_adapter_units_horizon_and_provenance():
    context = {"load_scope_model_assumption_acknowledged": True,
               "pv_conversion_assumption_acknowledged": True,
               "pv_conversion_factor_to_ac_equivalent": .95,
               "constant_efficiency_model_acknowledged": True,
               "pv_source": empty_case()["pv_source"]}
    data = from_eos(eos_case(), "b" * 64, context=context)
    assert data["data_kind"] == "archived_forecast"
    assert data["rows"][0]["import_eur_kwh"] == .1
    assert data["rows"][0]["load_wh"] == 200  # No false factor of four.
    assert data["e3dc"]["charge_efficiency"] == pytest.approx(.95 * .97)
    assert data["source_sha256"] == ["b" * 64]
    with pytest.raises(SimulationError):
        from_eos(eos_case(), "b" * 64, context={})


def test_actuals_adapter_reuses_existing_contract_and_never_splits_prices():
    row = empty_case()["rows"][0]
    actuals = {"schema_version": 1, "energy_kind": "measured_interval_wh",
        "origin": {"kind": "operator_meter_export", "source_artifact_sha256": "c" * 64,
                   "pv_basis": "ac", "battery_basis": "dc_bus",
                   "house_load_scope": "whole_site_including_loadpoints",
                   "tariff_basis": "retail_final_eur_kwh"},
        "energy": [{"start_utc": row["start_utc"], "end_utc": row["end_utc"],
                    "pv_wh": 0, "load_wh": 200}],
        "tariffs": [{"start_utc": row["start_utc"], "end_utc": row["end_utc"],
                     "retail_eur_kwh": .3}]}
    context = {"e3dc": empty_case()["e3dc"], "export_eur_kwh": .08,
               "pv_source": {"mode": "cached_weather"}}
    data = from_actuals(actuals, "d" * 64, context=context)
    assert data["data_kind"] == "measured"
    assert data["rows"][0]["load_wh"] == 200
    bad = copy.deepcopy(actuals)
    bad["tariffs"][0]["end_utc"] = "2026-06-18T00:05:00Z"
    with pytest.raises(SimulationError):
        from_actuals(bad, "d" * 64, context=context)

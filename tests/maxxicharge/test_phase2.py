import copy
from dataclasses import replace

import pytest
from maxxicharge_fixture import make

from ems_maxxicharge.adapter import journal
from ems_maxxicharge.capabilities import CONFIRMED
from ems_maxxicharge.comparison import compare, run_case
from ems_maxxicharge.config import Config, OperationConfig, SimulationError
from ems_maxxicharge.inputs import validate
from ems_maxxicharge.pv import generate


def case(count=8):
    data = make(days=1, seconds=3600)
    data["rows"] = data["rows"][:count]
    data["e3dc"]["initial_soc_percent"] = 25
    for row in data["rows"]:
        row["weather"].update(ghi=0, dni=0, dhi=0, solar_elevation_deg=-10)
    return data


def test_three_models_seven_expansions_and_no_assumed_grid_control():
    report = compare(case(), Config())
    assert report["simulation_schema"] == 2
    assert len(report["scenarios"]) == 13
    assert {c["operating_model"] for c in report["scenarios"].values()} == {
        "autonomous", "coordinated", "ideal"}
    assert report["scenarios"]["pv2_only"]["maxxi_config"] is None
    assert report["scenarios"]["pv3_only"]["extra_pv_wp"] == 3000
    assert report["scenarios"]["pv6_bat10__ideal"]["maxxi_input_units_assumed"] == 2
    for c in report["scenarios"].values():
        assert not c["grid_charging_optional_assumption"]
        assert abs(c["summary"]["balance_error_wh"]) < 1e-5
        assert c["summary"]["payback_years"] is None
        for r in c["rows"]:
            if r["maxxi"]:
                assert r["maxxi"]["charge_grid_wh"] == 0
    assert CONFIRMED["exact_discharge_setpoint_supported"] is False
    assert CONFIRMED["external_grid_charge_start_stop_confirmed"] is False
    assert CONFIRMED["virtual_smart_meter_from_e3dc_officially_supported"] is False


def test_ideal_is_proven_and_replays_in_existing_battery_physics():
    report = compare(case(), Config())
    for c in report["scenarios"].values():
        if c["operating_model"] != "ideal":
            continue
        assert c["solver"]["optimality_proven"] is True
        assert c["solver"]["mip_gap"] < 1e-7
        for r in c["rows"]:
            states = [s for s in (r["e3dc"], r["maxxi"]) if s]
            assert r["pv_wh"] + r["grid_import_wh"] + sum(s["start_wh"] for s in states) == pytest.approx(
                r["load_wh"] + r["grid_export_wh"] + r["curtailed_wh"]
                + r["losses_wh"] + sum(s["end_wh"] for s in states), abs=1e-5)
            for s in states:
                assert min(s["charge_grid_wh"] + s["charge_pv_wh"], s["discharge_wh"]) < 1e-6
        for model in ("autonomous", "coordinated"):
            reference = report["scenarios"][c["expansion"] + "__" + model]
            assert c["summary"]["inventory_adjusted_cost_eur"] <= reference["summary"]["inventory_adjusted_cost_eur"] + .001


def test_limits_only_journal_and_explicit_optional_grid_variants():
    report = compare(case(4), Config(operation=OperationConfig(optional_grid_charging=True)))
    assert len(report["scenarios"]) == 22
    for message in journal(report):
        assert message["payload"]["mode"] == "SIM"
        assert "intent" not in message["topic"]
        if message["topic"].endswith("/limits"):
            assert "__coordinated" in message["topic"]
            assert message["payload"]["exact_discharge_setpoint"] is None
            assert message["payload"]["external_grid_start_stop_confirmed"] is False
            assert "grid_charge_w" not in message["payload"]


def test_no_unlimited_direct_pv_and_3kwp_unit_limit():
    data = make(days=1, seconds=3600)
    data["rows"] = data["rows"][10:14]
    for row in data["rows"]:
        row["load_wh"] = 10000
        row["base_pv_wh"] = 0
    rows, e3dc = validate(data)
    cfg = Config(maxxi=replace(Config().maxxi, initial_soc_percent=100))
    panels, _ = generate(rows, data["pv_source"], cfg)
    for model in ("autonomous", "coordinated", "ideal"):
        c = run_case(rows, panels, e3dc, cfg, "pv3_bat5", model)
        for r in c["rows"]:
            assert r["maxxi"]["discharge_w"] <= 800 + 1e-6
            assert r["maxxi_ac_output_w"] <= 800 + 1e-6
        assert c["summary"]["curtailed_wh"] > 0
    too_big = replace(cfg, panels=tuple(replace(p, wp=2000) for p in cfg.panels))
    with pytest.raises(SimulationError):
        compare(data, too_big)


def test_costs_investment_storage_increment_and_e3dc_capability():
    cfg = Config(operation=OperationConfig(e3dc_coordination_enabled=True,
        pv_only_2kwp_investment_eur=1000, additional_3kwp_cost_eur=400))
    report = compare(case(), cfg)
    assert report["scenarios"]["pv2_bat5__coordinated"]["summary"]["investment_eur"] == 2500
    assert report["scenarios"]["pv3_bat5__coordinated"]["summary"]["investment_eur"] == 2900
    assert report["scenarios"]["pv3_only"]["summary"]["investment_eur"] == 1400
    for c in report["scenarios"].values():
        s = c["summary"]
        assert s["fixed_grid_cost_eur"] == pytest.approx(s["grid_import_wh"] / 1000 * .32)
        assert s["operating_cost_eur"] == pytest.approx(s["grid_cost_eur"] - s["feed_in_revenue_eur"] + s["wear_eur"])
        if c["maxxi_config"]:
            reference = c["storage_reference"]["summary"]["operating_cost_eur"]
            assert s["storage_increment_eur"] == pytest.approx(reference - s["operating_cost_eur"])
    coordinated = report["scenarios"]["pv2_bat5__coordinated"]
    assert all(r["limits"]["e3dc_coordination_enabled"] for r in coordinated["rows"])


def test_same_inputs_deterministic_and_not_modified():
    from ems_maxxicharge.inputs import canonical

    data = case(3)
    before = copy.deepcopy(data)
    one, two = compare(data, Config()), compare(data, Config())
    assert data == before
    assert canonical(one) == canonical(two)


def test_phase2_dashboard_and_admission_preserve_capability_boundary():
    from eos_pv_helper.dashboard_view import render, validate_sim_report

    report = compare(case(3), Config())
    assert validate_sim_report(report) is report
    html = render({"plans": [], "maxxicharge_sim": report})
    assert "Speichermehrwert" in html and "LUOX" in html and "Nettokosten" in html
    incomplete = copy.deepcopy(report)
    incomplete["historical_audit"] = {"message": "incomplete"}
    with pytest.raises(ValueError):
        validate_sim_report(incomplete)
    report["manufacturer_capabilities"] = {**report["manufacturer_capabilities"],
                                          "exact_discharge_setpoint_supported": True}
    with pytest.raises(ValueError):
        validate_sim_report(report)


def test_own_pv_and_battery_share_ac_limit_and_independent_model_can_overshoot():
    data = case(6)
    data["pv_source"] = {"mode": "cached_planes"}
    for i, row in enumerate(data["rows"]):
        row.update(load_wh=2000 if i < 2 else 0, base_pv_wh=0)
        row["planes"] = {name: {"basis": "ac_equivalent_front_wh_per_kwp", "wh_per_kwp":
            150 if i < 2 else 0, "tilt_deg": tilt, "azimuth_deg": 180}
            for name, tilt in (("suedhuette", 14), ("suedzaun", 90))}
    cfg = Config(maxxi=replace(Config().maxxi, initial_soc_percent=90))
    report = compare(data, cfg)
    for c in report["scenarios"].values():
        for row in c["rows"]:
            if row["maxxi"]:
                assert row["maxxi_ac_output_w"] <= 800 + 1e-6
            assert abs(row["balance_error_wh"]) < 1e-6
    assert report["scenarios"]["pv2_bat5__autonomous"]["summary"]["battery_export_wh"] > 0
    assert report["scenarios"]["pv2_bat5__ideal"]["summary"]["battery_export_wh"] == pytest.approx(0, abs=1e-5)


def test_unpriced_3kwp_increment_is_unknown_not_free():
    report = compare(case(2), Config())
    sums = report["scenarios"]["pv3_bat5__coordinated"]["summary"]
    assert sums["investment_eur"] is None
    assert sums["investment_base_eur"] == 2500
    assert sums["investment_additional_3kwp_eur"] is None
    assert report["scenarios"]["pv2_only"]["summary"]["investment_eur"] is None

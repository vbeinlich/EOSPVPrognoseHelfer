import copy
import json

import pytest
from test_energy_data import at, fixture, power_vehicle, run

from ems_maxxicharge.__main__ import main
from ems_maxxicharge.comparison import compare
from ems_maxxicharge.config import Config, SimulationError
from ems_maxxicharge.history import END, START
from ems_maxxicharge.prepared import from_prepared


def context():
    return {"e3dc": {"capacity_wh": 13000, "initial_soc_percent": 10,
                     "max_discharge_w": 6000, "max_pv_charge_w": 6000, "max_grid_charge_w": 0},
            "load_scope": "whole_site_including_loadpoints", "tariff_basis": "retail_final_eur_kwh",
            "tariff_aggregation": "energy_weighted_hour",
            "pv_source": {"mode": "reference_proxy", "proxy_acknowledged": True,
                          "latitude": 50, "longitude": 10, "reference_wp": 11000,
                          "reference_tilt_deg": 30, "reference_azimuth_deg": 180}}


def test_shared_preparation_drives_existing_13_cases_and_preserves_measurement_quality():
    records, config = fixture()
    data = from_prepared(run(records, config), context())
    result = compare(data, Config())
    assert len(result["scenarios"]) == 13
    assert result["coverage_hours"] == 2
    assert not result["historical_audit"]["historical_acceptance_passed"]
    assert not data["measurement_preparation"]["provisional_power_integration"]
    for case in result["scenarios"].values():
        assert abs(case["summary"]["balance_error_wh"]) < 1e-5


def test_power_integration_must_be_explicitly_provisional_in_report_and_html(tmp_path):
    records, config = fixture()
    power_vehicle(records, config)
    data = run(records, config)
    with pytest.raises(SimulationError, match="provisional"):
        from_prepared(data, context())
    settings = {**context(), "provisional_simulation_acknowledged": True}
    accepted = from_prepared(data, settings)
    assert accepted["measurement_preparation"]["provisional_power_integration"]
    assert not accepted["historical_audit"]["historical_acceptance_passed"]
    source, ctx, output = tmp_path / "prepared.json", tmp_path / "context.json", tmp_path / "run"
    source.write_text(json.dumps(data))
    ctx.write_text(json.dumps(settings))
    assert main(["--input", str(source), "--input-kind", "prepared", "--context", str(ctx),
                 "--phase2", "--output", str(output)]) == 0
    report = json.loads((output / "simulation.json").read_bytes())
    assert len(report["scenarios"]) == 13
    assert "VORLÄUFIG" in report["historical_audit"]["message"]
    assert "VORLÄUFIG" in (output / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("change", ["row", "status", "mapping", "source", "kind"])
def test_tampered_quality_or_inputs_cannot_enter_simulator(change):
    records, config = fixture()
    data = run(records, config)
    if change == "row":
        data["rows"][0]["load_wh"] = 1
    elif change == "status":
        data["audit"]["historical_acceptance_passed"] = True
    elif change == "mapping":
        data["mapping_sha256"] = "0" * 64
    elif change == "kind":
        data["data_kind"] = "measured"
    else:
        data["original_observations"][0]["value"] = 5
    with pytest.raises(SimulationError):
        from_prepared(data, context())


def test_gaps_cannot_be_admitted_even_with_provisional_acknowledgement():
    records, config = fixture()
    del records[0]
    data = run(records, config)
    with pytest.raises(SimulationError, match="Incomplete"):
        from_prepared(data, {**context(), "provisional_simulation_acknowledged": True})


def test_120_synthetic_hours_use_existing_historical_gates_without_real_claim():
    from datetime import datetime

    from eos_pv_helper.energy_data import prepare

    records, config = fixture(120)
    # Shift explicitly synthetic analytic test data; these are NOT November measurements.
    offset = START - datetime.fromisoformat(at())
    for r in records:
        for key in ("at", "start", "end"):
            if key in r:
                r[key] = (datetime.fromisoformat(r[key]) + offset).isoformat()
    data = prepare(records, config, START.isoformat(), END.isoformat(), as_of=END.isoformat())
    settings = {**context(), "historical_reference": True}
    prepared = from_prepared(data, settings)
    audit = prepared["historical_audit"]
    assert audit["original_hours"] == 120
    assert not audit["historical_acceptance_passed"]
    assert audit["source_kind"] == "synthetic"
    bad = copy.deepcopy(data)
    bad["mapping"]["data_kind"] = "measured"
    bad["data_kind"] = "measured"
    from eos_pv_helper.energy_data import prepare as reprepare

    bad = reprepare(bad["original_observations"], bad["mapping"],
                    START.isoformat(), END.isoformat(), as_of=END.isoformat())
    with pytest.raises(SimulationError, match="reference totals"):
        from_prepared(bad, settings)

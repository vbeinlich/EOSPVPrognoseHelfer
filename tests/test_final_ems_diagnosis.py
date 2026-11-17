import copy
import json

import pytest
from diagnose_ems_comparison import baseline_diagnosis, reference_experiments
from maxxicharge_fixture import make
from test_energy_data import at

from ems_maxxicharge.comparison import compare
from ems_maxxicharge.config import Config
from ems_maxxicharge.inputs import canonical


def analytic():
    measured, model, inputs, original = [], [], [], []
    for i, (grid, charge, discharge, price) in enumerate(((1500, 500, 0, 0.1), (500, 0, 500, 0.5))):
        key = {"start_utc": at(i), "end_utc": at(i + 1)}
        m = {
            **key,
            "load_wh": 1000,
            "base_pv_wh": 0,
            "grid_import_wh": grid,
            "grid_export_wh": 0,
            "battery_charge_wh": charge,
            "battery_discharge_wh": discharge,
            "import_eur_kwh": price,
            "grid_cost_eur": grid / 1000 * price,
            "soc_start_percent": 50,
            "soc_end_percent": 50,
            "soc_end_at_utc": at(i + 1),
            "soc_end_age_seconds": 0,
        }
        measured.append(m)
        model.append(
            {
                **key,
                "load_wh": 1000,
                "pv_wh": 0,
                "grid_import_wh": 1000,
                "grid_export_wh": 0,
                "grid_cost_eur": price,
                "e3dc": {
                    "charge_pv_wh": 0,
                    "charge_grid_wh": 0,
                    "discharge_wh": 0,
                    "losses_wh": 0,
                    "start_wh": 1000,
                    "soc_percent": 50,
                },
            }
        )
        inputs.append({**key, "import_eur_kwh": price})
        original.append(
            {**key, "soc_end_percent": "50", "tariff_hourly_mean_raw": str(price + 0.02)}
        )
    battery = {
        "capacity_wh": 2000,
        "initial_soc_percent": 50,
        "min_soc_percent": 0,
        "max_soc_percent": 100,
        "charge_efficiency": 0.9,
        "discharge_efficiency": 0.9,
    }
    return measured, model, inputs, original, battery


def test_exact_cost_identity_and_timing_effect_without_price_fitting():
    args = analytic()
    before = copy.deepcopy(args)
    result = baseline_diagnosis(*args)
    t = result["totals"]
    assert t["cost_delta_eur"] == pytest.approx(0.2)
    assert t["battery_charge_cost_eur"] == pytest.approx(-0.05)
    assert t["battery_discharge_cost_eur"] == pytest.approx(0.25)
    assert t["tariff_cost_eur"] == 0
    assert t["unexplained_cost_identity_residual_eur"] == pytest.approx(0, abs=1e-12)
    assert result["volume_vs_timing"]["quantity_at_observed_average_cost_eur"] == 0
    assert result["volume_vs_timing"]["hourly_distribution_effect_eur"] == pytest.approx(0.2)
    assert t["measured_repriced_raw_mean_delta_eur"] == pytest.approx(0.04)
    assert t["model_repriced_raw_mean_delta_eur"] == pytest.approx(0.04)
    assert args == before
    assert result["historical_acceptance_passed"] is False


def test_explicit_price_difference_is_separate_from_energy_volume():
    args = analytic()
    args[2][0]["import_eur_kwh"] = 0.12
    args[1][0]["grid_cost_eur"] = 0.12
    result = baseline_diagnosis(*args)
    assert result["totals"]["cost_delta_eur"] == pytest.approx(0.22)
    assert result["totals"]["tariff_cost_eur"] == pytest.approx(0.02)


def test_source_balance_residual_is_not_silently_corrected():
    args = analytic()
    args[0][0]["load_wh"] += 10
    result = baseline_diagnosis(*args)
    assert result["totals"]["cost_delta_eur"] == pytest.approx(0.2)
    assert result["totals"]["load_cost_eur"] == pytest.approx(-0.001)
    assert result["totals"]["meter_balance_cost_eur"] == pytest.approx(0.001)


@pytest.mark.parametrize("change", ["time", "duplicate", "length"])
def test_no_fitted_timestamp_shifts_or_dropped_intervals(change):
    args = analytic()
    if change == "time":
        args[1][0]["start_utc"] = at(seconds=1)
    elif change == "duplicate":
        args[3][1] = copy.deepcopy(args[3][0])
    else:
        args[1].pop()
    with pytest.raises(ValueError):
        baseline_diagnosis(*args)


def test_impossible_meter_boundary_under_assumptions_is_not_a_fitted_soc():
    args = analytic()
    args[4]["charge_efficiency"] = 0.1
    args[4]["discharge_efficiency"] = 0.1
    result = baseline_diagnosis(*args)["battery_boundary_diagnostic"]
    assert result["implied_end_internal_wh"] < 0
    assert result["measured_counter_trajectory_incompatible_with_configured_bounds"] is True
    assert result["parameters_fitted_or_applied"] is False


def test_missing_alternative_tariff_is_not_zero_or_a_claimed_validation():
    args = analytic()
    for row in args[3]:
        row.pop("tariff_hourly_mean_raw")
    result = baseline_diagnosis(*args)
    assert result["totals"]["model_repriced_raw_mean_delta_eur"] is None
    assert result["totals"]["cost_delta_eur"] == pytest.approx(0.2)


def test_offline_reference_experiments_reuse_engine_and_preserve_originals():
    data = make(days=1, seconds=3600)
    data["rows"] = data["rows"][9:13]
    config = Config()
    result = json.loads(canonical(compare(data, config)))
    original_data, original_result = canonical(data), canonical(result)
    diagnostic = reference_experiments(data, result)
    assert len(diagnostic["storage_comparisons"]) == 9
    for item in diagnostic["ab"].values():
        assert item["max_summary_delta_to_A"] < 1e-7
        assert item["explicit_change"] == {"price_hold_enabled": False}
    for item in diagnostic["storage_comparisons"]:
        assert item["stored_pv_only_ac_limit_w"] is None
        assert item["matched_pv_only_ac_limit_w"] == 800
        assert item["storage_capex_premium_eur"] is None
        assert item["annual_savings_eur"] is None
        assert item["payback_years"] is None
        assert item["same_ac_pv_only_net_cost_eur"] - item[
            "pv_with_storage_net_cost_eur"
        ] == pytest.approx(item["same_ac_storage_increment_cash_eur"])
    assert diagnostic["same_ac_reference_config_sha256"] != result["config_sha256"]
    assert canonical(data) == original_data and canonical(result) == original_result
    changed = copy.deepcopy(result)
    changed["engine_code_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="revision"):
        reference_experiments(data, changed)


def test_stored_diagnostic_pipeline_manifest_and_original_protection(tmp_path):
    import csv
    import hashlib
    import io

    from diagnose_ems_comparison import main
    from test_energy_data import fixture, run

    from ems_maxxicharge.prepared import from_prepared

    records, mapping = fixture()
    prepared = run(records, mapping)
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream, fieldnames=["start_utc", "end_utc", "soc_end_percent", "tariff_hourly_mean_raw"]
    )
    writer.writeheader()
    for row in prepared["rows"]:
        writer.writerow(
            {
                "start_utc": row["start_utc"],
                "end_utc": row["end_utc"],
                "soc_end_percent": 10,
                "tariff_hourly_mean_raw": 0.3,
            }
        )
    raw = stream.getvalue().encode()
    original = tmp_path / "original.csv"
    original.write_bytes(raw)
    prepared["source_file_sha256"] = hashlib.sha256(raw).hexdigest()
    context = {
        "e3dc": {
            "capacity_wh": 13000,
            "initial_soc_percent": 10,
            "max_discharge_w": 6000,
            "max_pv_charge_w": 6000,
            "max_grid_charge_w": 0,
        },
        "pv_source": {
            "mode": "reference_proxy",
            "proxy_acknowledged": True,
            "latitude": 50,
            "longitude": 10,
            "reference_wp": 11000,
            "reference_tilt_deg": 30,
            "reference_azimuth_deg": 180,
        },
    }
    data = from_prepared(prepared, context)
    result = compare(data, Config())
    measured_path = tmp_path / "prepared.json"
    measured_path.write_bytes(canonical(prepared))
    simulation = tmp_path / "simulation"
    simulation.mkdir()
    (simulation / "simulation.json").write_bytes(canonical(result))
    (simulation / "normalized-input.json").write_bytes(canonical(data))
    output = tmp_path / "diagnosis"
    args = [
        "--prepared",
        str(measured_path),
        "--simulation-dir",
        str(simulation),
        "--hourly-source",
        str(original),
        "--output",
        str(output),
    ]
    assert main(args) == 0
    manifest = json.loads((output / "manifest.json").read_bytes())
    for name, sha in manifest["artifacts_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == sha
    assert len(list(csv.DictReader((output / "baseline-hourly.csv").open()))) == 2
    assert len(list(csv.DictReader((output / "storage-comparison.csv").open()))) == 9
    assert original.read_bytes() == raw
    assert main(args) == 2

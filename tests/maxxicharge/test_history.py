import copy
import csv
import io
from datetime import timedelta

import pytest

from ems_maxxicharge.config import SimulationError
from ems_maxxicharge.history import ENERGY, START, import_csv


def fixture():
    columns = ["start_utc", "end_utc", *ENERGY, "import_eur_kwh", "export_eur_kwh",
               "soc_start_percent", "soc_end_percent", "soc_start_at_utc", "soc_end_at_utc"]
    rows = []
    for i in range(120):
        at, end = START + timedelta(hours=i), START + timedelta(hours=i + 1)
        rows.append({**dict.fromkeys(ENERGY, 0), "load_wh": 1000, "grid_import_wh": 1000,
            "start_utc": at.isoformat(), "end_utc": end.isoformat(),
            "import_eur_kwh": .3, "export_eur_kwh": .08,
            "soc_start_percent": 10, "soc_end_percent": 10,
            "soc_start_at_utc": at.isoformat(), "soc_end_at_utc": end.isoformat()})
    context = {"energy_kind": "measured_interval_integrals", "data_kind": "synthetic",
        "load_scope": "whole_site_including_loadpoints", "tariff_basis": "retail_final_eur_kwh",
        "tariff_aggregation": "constant_within_hour", "battery_basis": "ac_bus",
        "units": dict.fromkeys(ENERGY, "Wh"), "delimiter": ",", "decimal_separator": ".",
        "e3dc": {"capacity_wh": 13000, "initial_soc_percent": 10,
                  "max_discharge_w": 6000, "max_pv_charge_w": 6000, "max_grid_charge_w": 0},
        "pv_source": {"mode": "reference_proxy", "proxy_acknowledged": True, "latitude": 50,
                      "longitude": 10, "reference_wp": 11000,
                      "reference_tilt_deg": 30, "reference_azimuth_deg": 180}}
    return columns, rows, context


def encode(columns, rows, delimiter=","):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns, delimiter=delimiter)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def test_120_original_hours_cost_math_and_no_false_real_acceptance():
    columns, rows, context = fixture()
    data = import_csv(encode(columns, rows), context)
    audit = data["historical_audit"]
    assert audit["original_hours"] == 120
    assert audit["reference_totals"]["load_wh"] == 120000
    assert audit["reference_totals"]["grid_cost_eur"] == pytest.approx(36)
    assert audit["reference_totals"]["fixed_grid_cost_eur"] == pytest.approx(38.4)
    assert audit["historical_acceptance_passed"] is False
    assert audit["efficiency_fit"]["status"] == "not_identifiable"


def test_8_and_9_november_are_excluded_without_filling_their_gaps():
    columns, rows, context = fixture()
    excluded = [{**dict.fromkeys(columns, ""), "start_utc": date}
                for date in ("2026-11-08T10:00:00+01:00", "2026-11-09T15:00:00+01:00")]
    data = import_csv(encode(columns, excluded + rows), context)
    assert len(data["rows"]) == 120
    assert data["historical_audit"]["excluded_rows"] == 2


@pytest.mark.parametrize("failure", ["gap", "duplicate", "power", "missing", "soc_future",
    "soc_old", "balance", "reference", "unit", "price_nan", "unknown_tariff", "counter"])
def test_bad_or_unproven_history_blocks(failure):
    columns, rows, context = fixture()
    if failure == "gap":
        del rows[13]
    elif failure == "duplicate":
        rows[13] = copy.deepcopy(rows[12])
    elif failure == "power":
        context["energy_kind"] = "hourly_mean_w"
    elif failure == "missing":
        rows[3]["load_wh"] = ""
    elif failure == "soc_future":
        rows[3]["soc_start_at_utc"] = rows[3]["end_utc"]
    elif failure == "soc_old":
        rows[3]["soc_start_at_utc"] = rows[2]["start_utc"]
    elif failure == "balance":
        rows[3]["grid_import_wh"] = 9000
    elif failure == "reference":
        context["data_kind"] = "measured"
    elif failure == "unit":
        context["units"]["load_wh"] = "W"
    elif failure == "price_nan":
        rows[3]["import_eur_kwh"] = "nan"
    elif failure == "unknown_tariff":
        context["tariff_aggregation"] = "unweighted_quarter_hour_mean"
    else:
        context["energy_kind"] = "cumulative_counter_kwh"
    with pytest.raises(SimulationError):
        import_csv(encode(columns, rows), context)


def test_soc_model_problem_is_a_visible_failed_calibration_not_a_fitted_fact():
    columns, rows, context = fixture()
    for i, row in enumerate(rows):
        row["soc_start_percent"] = 10 + i * .2
        row["soc_end_percent"] = 10 + (i + 1) * .2
    context["soc_model_tolerance_wh"] = 1
    data = import_csv(encode(columns, rows), context)
    assert data["historical_audit"]["status"] == "warnings"
    assert not data["historical_audit"]["historical_acceptance_passed"]
    assert data["historical_audit"]["efficiency_fit"]["applied_to_simulation"] is False


def test_csv_cli_preserves_original_hash_and_synthetic_admission(tmp_path):
    import hashlib
    import json

    from ems_maxxicharge.__main__ import main

    columns, rows, context = fixture()
    source, settings, output = tmp_path / "original.csv", tmp_path / "context.json", tmp_path / "run"
    raw = encode(columns, rows)
    source.write_bytes(raw)
    settings.write_text(json.dumps(context), encoding="utf-8")
    assert main(["--input", str(source), "--input-kind", "history_csv", "--context", str(settings),
                 "--phase2", "--output", str(output)]) == 0
    report = json.loads((output / "simulation.json").read_bytes())
    assert report["input_file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["coverage_hours"] == 120 and len(report["scenarios"]) == 13
    assert report["data_kind"] == "synthetic"
    assert not report["historical_audit"]["historical_acceptance_passed"]
    manifest = json.loads((output / "manifest.json").read_bytes())
    assert manifest["complete"] is True
    for name, expected in manifest["artifacts_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected
    assert source.read_bytes() == raw

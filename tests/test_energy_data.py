"""Independent analytic streams, not a reconstruction of November measurements."""

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from eos_pv_helper.energy_data import (
    EnergyDataError,
    MeasurementBuffer,
    observations_from_ha,
    prepare,
    timestamp,
)
from eos_pv_helper.energy_data_cli import export_csv, main

START = datetime(2026, 6, 1, tzinfo=UTC)


def at(hour=0, seconds=0):
    return (START + timedelta(hours=hour, seconds=seconds)).isoformat()


def fixture(hours=2):
    rates = {"house_wh": 300, "heatpump_wh": 500, "vehicle_wh": 200,
             "base_pv_wh": 100, "grid_import_wh": 900, "grid_export_wh": 0,
             "battery_charge_wh": 0, "battery_discharge_wh": 0, "grid_cost_eur": .27}
    config = {"schema_version": 1, "data_kind": "synthetic", "timezone": "Europe/Berlin",
              "tariff_basis": "retail_final_eur_kwh", "grid_cost_scope": "energy_import_only",
              "load_components": ["house_wh", "heatpump_wh", "vehicle_wh"],
              "metrics": {}, "excluded_entities": ["heatpump_duplicate"]}
    records = []
    for name, delta in rates.items():
        unit = "EUR" if name == "grid_cost_eur" else "Wh"
        source = {"entity_id": name, "kind": "counter", "unit": unit}
        if unit == "Wh":
            source["basis"] = "ac_bus"
        config["metrics"][name] = {"sources": [source]}
        if name in config["load_components"]:
            config["metrics"][name]["covers"] = [name]
        for h in range(hours + 1):
            records.append({"entity_id": name, "at": at(h), "value": 10000 + h * delta, "unit": unit})
    config["metrics"]["soc_percent"] = {"sources": [
        {"entity_id": "soc", "kind": "state", "unit": "%"}]}
    config["metrics"]["export_eur_kwh"] = {"sources": [
        {"entity_id": "feed", "kind": "interval", "unit": "EUR/kWh"}]}
    for h in range(hours + 1):
        records.append({"entity_id": "soc", "at": at(h), "value": 10, "unit": "%"})
        if h < hours:
            records.append({"entity_id": "feed", "start": at(h), "end": at(h + 1), "value": .08, "unit": "EUR/kWh"})
    return records, config


def run(records, config, hours=2, as_of=None):
    return prepare(records, config, at(), at(hours), as_of=as_of or at(hours))


def power_vehicle(records, config, hours=2):
    records[:] = [r for r in records if r["entity_id"] != "vehicle_wh"]
    config["metrics"]["vehicle_wh"]["sources"] = [
        {"entity_id": "power", "kind": "power", "unit": "W", "basis": "ac_bus",
         "integration": "left_hold", "max_gap_seconds": 300}]
    for second in range(0, hours * 3600 + 1, 300):
        records.append({"entity_id": "power", "at": at(seconds=second), "value": 200, "unit": "W"})


def test_same_history_and_arriving_stream_and_idempotence():
    records, config = fixture()
    original = copy.deepcopy(records)
    history = run(records, config)
    buffer = MeasurementBuffer(config)
    for record in reversed(records):
        buffer.extend([record])
    incremental = buffer.prepare(at(), at(2), as_of=at(2))
    assert incremental["rows"] == history["rows"]
    buffer.extend(records)  # repeated history windows cannot double count
    assert buffer.prepare(at(), at(2), as_of=at(2))["rows"] == history["rows"]
    assert history["audit"]["status"] == "passed"
    assert history["audit"]["historical_acceptance_passed"] is False
    assert history["rows"][0]["load_wh"] == 1000
    assert history["rows"][0]["site_balance_error_wh"] == 0
    assert history["rows"][0]["import_eur_kwh"] == pytest.approx(.3)
    assert records == original


def test_delayed_arrival_repairs_only_when_original_boundary_is_present():
    records, config = fixture()
    record = next(r for r in records if r["entity_id"] == "house_wh" and r["at"] == at(1))
    record["received_at"] = at(1, 120)
    early = run(records, config, as_of=at(1))
    assert early["rows"][0]["house_wh"] is None
    late = run(records, config)
    assert late["rows"][0]["house_wh"] == 300
    assert early["rows"][0]["house_wh"] is None
    # Actual observation at 01:02 is not re-labelled 01:00, even if plausible.
    record["at"] = at(1, 120)
    assert run(records, config)["rows"][0]["house_wh"] is None


def test_late_revision_is_explicit_and_conflict_does_not_choose_arbitrarily():
    records, config = fixture()
    record = next(r for r in records if r["entity_id"] == "house_wh" and r["at"] == at(1))
    records.append({**record, "value": 10301, "received_at": at(1, 10)})
    assert run(records, config)["rows"][0]["house_wh"] == 301
    records[-1].pop("received_at")
    with pytest.raises(EnergyDataError, match="Conflicting"):
        run(records, config)


def test_counter_reset_missing_boundaries_and_recovery():
    records, config = fixture(3)
    for record in records:
        if record["entity_id"] == "house_wh" and record["at"] in (at(1), at(2), at(3)):
            record["value"] -= 10300
    result = run(records, config, 3)
    assert result["rows"][0]["house_wh"] is None
    assert result["rows"][1]["house_wh"] == 300
    assert "counter_reset" in str(result["rows"][0]["quality"]["house_wh"])
    records[:] = [r for r in records if not (r["entity_id"] == "heatpump_wh" and r["at"] == at(1))]
    result = run(records, config, 3)
    assert all(result["rows"][i]["heatpump_wh"] is None for i in (0, 1))
    assert result["rows"][2]["heatpump_wh"] == 500
    assert result["audit"]["totals_covered_intervals"]["heatpump_wh"] == 1


def test_power_integration_preference_and_no_stale_fill():
    records, config = fixture()
    power_vehicle(records, config)
    result = run(records, config)
    assert result["rows"][0]["vehicle_wh"] == 200
    assert result["rows"][0]["quality"]["vehicle_wh"]["status"] == "derived_power_left_hold"
    source = {"entity_id": "direct_ev", "kind": "interval", "unit": "Wh", "basis": "ac_bus"}
    config["metrics"]["vehicle_wh"]["sources"].append(source)
    records.append({"entity_id": "direct_ev", "start": at(), "end": at(1), "value": 201, "unit": "Wh"})
    assert run(records, config)["rows"][0]["vehicle_wh"] == 201
    records[:] = [r for r in records if not (r["entity_id"] == "power" and r["at"] == at(1, 300))]
    assert run(records, config)["rows"][1]["vehicle_wh"] is None


def test_unknown_power_interrupts_coverage_and_is_not_zero():
    records, config = fixture()
    power_vehicle(records, config)
    next(r for r in records if r["entity_id"] == "power" and r["at"] == at(seconds=600))["value"] = "unavailable"
    result = run(records, config)
    assert result["rows"][0]["vehicle_wh"] is None
    assert result["rows"][0]["load_wh"] is None
    assert result["rows"][0]["balanced_load_wh"] == 1000
    assert result["rows"][1]["vehicle_wh"] == 200


def test_entirely_missing_quantity_does_not_become_zero_in_summary():
    records, config = fixture()
    records[:] = [r for r in records if r["entity_id"] != "vehicle_wh"]
    result = run(records, config)
    assert result["audit"]["totals"]["vehicle_wh"] is None
    assert result["audit"]["totals"]["load_wh"] is None
    assert result["audit"]["totals"]["balanced_load_wh"] == 2000
    assert "import_eur_kwh" not in result["audit"]["totals"]


def test_prederived_interval_energy_never_becomes_a_direct_measurement():
    records, config = fixture()
    source = {"entity_id": "ev_archive", "kind": "interval", "unit": "Wh", "basis": "ac_bus",
              "derivation": "derived_power_left_hold"}
    config["metrics"]["vehicle_wh"]["sources"] = [source]
    for h in range(2):
        records.append({"entity_id": "ev_archive", "start": at(h), "end": at(h + 1), "value": 200, "unit": "Wh"})
    result = run(records, config)
    assert result["rows"][0]["quality"]["vehicle_wh"]["status"] == "derived_power_left_hold"


def test_wide_csv_column_projection_uses_same_adapter_and_retains_original_rows(tmp_path):
    from eos_pv_helper.energy_data_cli import read_observations

    _, config = fixture()
    config["metrics"]["house_wh"]["sources"] = [
        {"entity_id": "house_csv", "kind": "interval", "unit": "Wh", "basis": "ac_bus",
         "derivation": "derived_counter", "csv": {"value": "old_load_column", "start": "start", "end": "end"}}]
    raw = ('start,end,old_load_column\n' + at() + ',' + at(1) + ',300\n').encode()
    observations = read_observations(raw, "wide_csv", config)
    assert observations[0]["original"]["old_load_column"] == "300"
    data = run(observations, config)
    assert data["rows"][0]["house_wh"] == 300
    assert data["rows"][0]["heatpump_wh"] is None
    assert data["rows"][0]["load_wh"] is None
    assert data["rows"][0]["quality"]["house_wh"]["status"] == "derived_counter"


@pytest.mark.parametrize("problem", ["scope", "entity", "excluded", "component"])
def test_duplicate_consumer_protection(problem):
    records, config = fixture()
    if problem == "scope":
        config["metrics"]["vehicle_wh"]["covers"] = ["heatpump_wh"]
    elif problem == "entity":
        config["metrics"]["vehicle_wh"]["sources"][0]["entity_id"] = "heatpump_wh"
    elif problem == "excluded":
        config["metrics"]["vehicle_wh"]["sources"][0]["entity_id"] = "heatpump_duplicate"
    else:
        config["load_components"].append("vehicle_wh")
    with pytest.raises(EnergyDataError):
        run(records, config)


def test_new_consumer_without_code_changes_and_balance_violation():
    records, config = fixture()
    config["metrics"]["pool_wh"] = {"covers": ["pool"], "sources": [
        {"entity_id": "pool", "kind": "interval", "unit": "Wh", "basis": "ac_bus"}]}
    config["load_components"].append("pool_wh")
    for h in range(2):
        records.append({"entity_id": "pool", "start": at(h), "end": at(h + 1), "value": 100, "unit": "Wh"})
    result = run(records, config)
    assert result["rows"][0]["load_wh"] == 1100
    assert result["rows"][0]["site_balance_error_wh"] == -100
    assert result["rows"][0]["status"] == "failed"
    assert "site_balance_exceeds_tolerance" in result["rows"][0]["issues"]


def test_direct_subintervals_aggregate_but_coarse_measurements_never_split():
    records, config = fixture()
    config["metrics"]["house_wh"]["sources"] = [
        {"entity_id": "house_energy", "kind": "interval", "unit": "kWh", "basis": "ac_bus"}]
    for second in range(0, 3600, 900):
        records.append({"entity_id": "house_energy", "start": at(seconds=second),
                        "end": at(seconds=second + 900), "value": .075, "unit": "kWh"})
    assert run(records, config)["rows"][0]["house_wh"] == pytest.approx(300)
    records.append({"entity_id": "house_energy", "start": at(1), "end": at(3), "value": .6, "unit": "kWh"})
    assert run(records, config, as_of=at(3))["rows"][1]["house_wh"] is None
    records.append({"entity_id": "house_energy", "start": at(), "end": at(1), "value": .3, "unit": "kWh"})
    with pytest.raises(EnergyDataError, match="overlap"):
        run(records, config)


def test_dc_boundary_conversion_is_shared_and_requires_efficiencies():
    records, config = fixture()
    config["metrics"]["base_pv_wh"]["sources"][0]["basis"] = "dc_bus"
    with pytest.raises(EnergyDataError):
        run(records, config)
    config["inverter_dc_to_ac_efficiency"] = .9
    assert run(records, config)["rows"][0]["base_pv_wh"] == 90
    assert "+dc_to_ac" in run(records, config)["rows"][0]["quality"]["base_pv_wh"]["status"]


def test_soc_original_time_and_future_or_stale_value_exclusion():
    records, config = fixture()
    record = next(r for r in records if r["entity_id"] == "soc" and r["at"] == at(1))
    record["at"] = at(1, -30)
    data = run(records, config)
    assert data["rows"][0]["soc_end_at_utc"] == at(1, -30)
    record["at"] = at(1, 1)
    assert run(records, config)["rows"][0]["soc_end_percent"] is None
    record["at"] = at(1, -61)
    assert run(records, config)["rows"][0]["soc_end_percent"] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -1])
def test_invalid_energy_never_passes(value):
    records, config = fixture()
    records[0]["value"] = value
    with pytest.raises((EnergyDataError, ValueError)):
        run(records, config)


def test_negative_measured_cost_and_zero_import_do_not_invent_tariff():
    records, config = fixture()
    for r in records:
        if r["entity_id"] == "grid_cost_eur":
            r["value"] = 10 - (datetime.fromisoformat(r["at"]) - START).total_seconds() / 3600 * .09
    assert run(records, config)["rows"][0]["import_eur_kwh"] == pytest.approx(-.1)
    for r in records:
        if r["entity_id"] == "grid_import_wh":
            r["value"] = 0
    result = run(records, config)
    assert result["rows"][0]["import_eur_kwh"] is None
    assert result["audit"]["status"] == "incomplete"


@pytest.mark.parametrize("wall", ["2026-03-29T02:00:00", "2026-10-25T02:00:00"])
def test_berlin_ambiguous_and_nonexistent_times_rejected(wall):
    with pytest.raises(EnergyDataError):
        timestamp(wall, {"timezone": "Europe/Berlin", "naive_local_time_acknowledged": True})


def test_real_dst_offsets_preserve_distinct_hours():
    a = timestamp("2026-10-25T02:00:00+02:00", {})
    b = timestamp("2026-10-25T02:00:00+01:00", {})
    assert (b - a).total_seconds() == 3600


def test_ha_adapter_preserves_source_object_and_original_timestamp():
    source = {"entity_id": "power", "last_updated": "2026-06-01T02:00:00+02:00",
              "state": "200", "attributes": {"unit_of_measurement": "W"}}
    result = observations_from_ha([[source]])
    assert result[0]["at"] == source["last_updated"]
    assert result[0]["original"] == source
    result[0]["original"]["state"] = "999"
    assert source["state"] == "200"


def test_private_cli_exports_quality_and_originals_without_overwrite(tmp_path):
    records, config = fixture()
    source, mapping, out = tmp_path / "original.json", tmp_path / "mapping.json", tmp_path / "prepared"
    raw = json.dumps({"observations": records}).encode()
    source.write_bytes(raw)
    mapping.write_text(json.dumps(config))
    args = ["--input", str(source), "--mapping", str(mapping), "--start", at(),
            "--end", at(2), "--as-of", at(2), "--output", str(out)]
    assert main(args) == 0
    assert (out / "original-export.bin").read_bytes() == raw
    assert source.read_bytes() == raw
    data = json.loads((out / "prepared.json").read_bytes())
    assert b"derived_counter" in export_csv(data)
    assert b"site_balance_error_wh" in (out / "corrected.csv").read_bytes()
    assert main(args) == 2
    assert data["original_observations"] == records


def test_incomplete_cli_retains_diagnostics_but_exit_code_is_not_success(tmp_path):
    records, config = fixture()
    records[:] = [r for r in records if r["entity_id"] != "house_wh"]
    source, mapping, out = tmp_path / "source.json", tmp_path / "mapping.json", tmp_path / "out"
    source.write_text(json.dumps({"observations": records}))
    mapping.write_text(json.dumps(config))
    assert main(["--input", str(source), "--mapping", str(mapping), "--start", at(),
                 "--end", at(2), "--as-of", at(2), "--output", str(out)]) == 3
    assert json.loads((out / "audit.json").read_bytes())["complete_intervals"] == 0


def test_shared_projection_into_existing_plan_actual_reader():
    from eos_pv_helper.energy_data import as_actuals, canonical
    from eos_pv_helper.plan_actual import Actuals

    records, config = fixture()
    with pytest.raises(EnergyDataError, match="never synthetic"):
        as_actuals(run(records, config))
    config["data_kind"] = "measured"
    prepared = run(records, config)
    data = as_actuals(prepared)
    reader = Actuals(canonical(data))
    assert reader.total("load_wh", START, START + timedelta(hours=2)) == 2000
    assert reader.cash_cost(START, START + timedelta(hours=2)) == pytest.approx(.54)
    assert reader.measured_cash_cost(START, START + timedelta(hours=2)) == pytest.approx(.54)
    assert len(reader.import_weighted_tariffs) == 2
    assert data["measurement_preparation"]["interval_quality"][0]["quality"] == prepared["rows"][0]["quality"]
    assert reader.soc_at(START)[0] == 10
    assert reader.battery_dc is False
    config.update(inverter_ac_to_dc_efficiency=.9, inverter_dc_to_ac_efficiency=.8)
    reader = Actuals(canonical(as_actuals(run(records, config))))
    assert reader.battery_dc is True
    assert reader.total("battery_discharge_dc_wh", START, START + timedelta(hours=2)) == 0


def test_cost_reset_marked_explicitly_does_not_become_negative_price():
    records, config = fixture()
    r = next(r for r in records if r["entity_id"] == "grid_cost_eur" and r["at"] == at(1))
    r["reset"] = True
    result = run(records, config)
    assert result["rows"][0]["grid_cost_eur"] is None
    assert result["rows"][1]["grid_cost_eur"] is not None


def test_revision_is_deterministic_under_reordered_arrivals():
    records, config = fixture()
    r = next(r for r in records if r["entity_id"] == "house_wh" and r["at"] == at(1))
    records.append({**r, "value": 10301, "received_at": at(1, 10)})
    assert run(records, config)["rows"] == run(list(reversed(records)), config)["rows"]


def test_actual_future_measurements_do_not_pass_by_choosing_future_watermark():
    records, config = fixture()
    config["data_kind"] = "measured"
    future = datetime.now(UTC) + timedelta(days=10)
    result = prepare(records, config, future.isoformat(), (future + timedelta(hours=1)).isoformat(),
                     as_of=(future + timedelta(hours=2)).isoformat())
    assert result["rows"][0]["status"] == "incomplete"


@pytest.mark.parametrize("filename", ["energy-mapping.example.json", "energy-wide-history.example.json"])
def test_real_example_mapping_rejects_heatpump_alias_as_vehicle(filename):
    from pathlib import Path

    from eos_pv_helper.energy_data import validate_mapping

    config = json.loads((Path(__file__).parents[1] / "simulator" / filename).read_bytes())
    validate_mapping(config)
    source = config["metrics"]["vehicle_barn_wh"]["sources"][0]
    assert source["entity_id"] == "sensor.evcc_scheune_charge_power"
    source["entity_id"] = "sensor.evcc_m_tec_evcc_charge_power"
    with pytest.raises(EnergyDataError, match="excluded"):
        validate_mapping(config)


def test_reported_november_aggregate_arithmetic_is_not_hourly_evidence():
    from pathlib import Path

    from eos_pv_helper.energy_data import site_balance

    reference = json.loads((Path(__file__).parent / "fixtures/energy-november-reference.json").read_bytes())
    values = reference["totals"]
    assert values["house_wh"] + values["heatpump_wh"] + values["vehicle_barn_wh"] == 227940
    site, error = site_balance(values)
    assert site == 227884
    assert error == -56
    assert "NOT 120 original hours" in reference["provenance"]


def test_reference_regression_requires_real_originals_and_exact_coverage():
    from check_energy_regression import check

    records, config = fixture()
    data = run(records, config)
    reference = {"intervals": 2, "start_utc": at(), "end_utc": at(2),
                 "totals": {"load_wh": 2000}, "tolerances": {"default_wh": 0}}
    with pytest.raises(EnergyDataError):
        check(data, reference)
    config["data_kind"] = "measured"
    report = check(run(records, config), reference)
    assert report["status"] == "passed" and report["historical_acceptance_passed"] is False
    reference["totals"]["load_wh"] = 1999
    with pytest.raises(EnergyDataError, match="differ"):
        check(run(records, config), reference)


def test_conflicting_explicit_tariff_and_measured_cost_block_admission():
    records, config = fixture()
    config["metrics"]["import_eur_kwh"] = {"sources": [
        {"entity_id": "tariff", "kind": "interval", "unit": "EUR/kWh"}]}
    records.append({"entity_id": "tariff", "start": at(), "end": at(1), "value": .5, "unit": "EUR/kWh"})
    result = run(records, config)
    assert result["rows"][0]["status"] == "failed"
    assert "measured_cost_and_tariff_disagree" in result["rows"][0]["issues"]


def test_original_euro_symbol_is_preserved_as_declared_cost_unit():
    records, config = fixture()
    config["metrics"]["grid_cost_eur"]["sources"][0]["unit"] = "€"
    for r in records:
        if r["entity_id"] == "grid_cost_eur":
            r["unit"] = "€"
    assert run(records, config)["audit"]["totals"]["grid_cost_eur"] == pytest.approx(.54)


def test_private_original_120_hour_regression_if_supplied():
    import os
    from pathlib import Path

    from check_energy_regression import check

    path = os.environ.get("EMS_PRIVATE_PREPARED_REFERENCE")
    if not path:
        pytest.skip("Original November hours not supplied; aggregate reference is not an hourly fixture")
    reference = json.loads((Path(__file__).parent / "fixtures/energy-november-reference.json").read_bytes())
    assert check(json.loads(Path(path).read_bytes()), reference)["status"] == "passed"


def test_stale_soc_preserves_original_observation_without_using_it_as_boundary_value():
    records, config = fixture()
    record = next(r for r in records if r["entity_id"] == "soc" and r["at"] == at(1))
    record["at"] = at(1, -120)
    row = run(records, config)["rows"][0]
    assert row["soc_end_percent"] is None
    assert row["soc_end_at_utc"] == at(1, -120)
    assert row["soc_end_age_seconds"] == 120
    detail = row["quality"]["soc_end_percent"]["rejected_candidates"][0]
    assert detail["issue"] == "stale_boundary_soc" and detail["observed_percent"] == 10


def test_original_five_minute_means_integrate_over_explicit_intervals_without_left_hold():
    records, config = fixture()
    records[:] = [r for r in records if r["entity_id"] != "vehicle_wh"]
    config["metrics"]["vehicle_wh"]["sources"] = [
        {"entity_id": "mean_ev", "kind": "mean_power", "unit": "W", "basis": "ac_bus",
         "mean_interval_seconds": 300}]
    # Irregular alternating 0/400 W means give precisely 200 Wh each hour.
    for second in range(0, 7200, 300):
        records.append({"entity_id": "mean_ev", "start": at(seconds=second), "end": at(seconds=second + 300),
                        "value": 400 if second % 600 else 0, "unit": "W"})
    data = run(records, config)
    assert data["rows"][0]["vehicle_wh"] == pytest.approx(200)
    assert data["rows"][0]["quality"]["vehicle_wh"]["status"] == "derived_interval_mean_power"
    detail = data["rows"][0]["quality"]["vehicle_wh"]
    assert "original_value" not in detail
    assert detail["interval_mean_integration"]["energy_wh"] == pytest.approx(200)
    config["interval_seconds"] = 900
    assert run(records, config)["rows"][0]["vehicle_wh"] == pytest.approx(400 / 12)
    config["interval_seconds"] = 3600
    records.pop()
    assert run(records, config)["rows"][1]["vehicle_wh"] is None


@pytest.mark.parametrize("coverage", ["11/12", "12/13", "", None])
def test_imported_mean_energy_with_partial_or_unknown_coverage_is_missing(coverage):
    records, config = fixture()
    config["metrics"]["vehicle_wh"]["sources"] = [
        {"entity_id": "ev_derived", "kind": "interval", "unit": "Wh", "basis": "ac_bus",
         "derivation": "derived_interval_mean_power", "mean_interval_seconds": 300}]
    records.append({"entity_id": "ev_derived", "start": at(), "end": at(1), "value": 200,
                    "unit": "Wh", "mean_power_coverage": coverage})
    assert run(records, config)["rows"][0]["vehicle_wh"] is None


def test_imported_mean_energy_retains_coverage_and_correct_provenance():
    records, config = fixture()
    config["metrics"]["vehicle_wh"]["sources"] = [
        {"entity_id": "ev_derived", "kind": "interval", "unit": "Wh", "basis": "ac_bus",
         "derivation": "derived_interval_mean_power", "mean_interval_seconds": 300}]
    records.append({"entity_id": "ev_derived", "start": at(), "end": at(1), "value": 200,
                    "unit": "Wh", "mean_power_coverage": "12/12"})
    row = run(records, config)["rows"][0]
    assert row["vehicle_wh"] == 200
    assert row["quality"]["vehicle_wh"]["status"] == "derived_interval_mean_power"

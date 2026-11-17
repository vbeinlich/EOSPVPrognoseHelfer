"""Synthetic fixed-control validation; no historical forecast invention or search."""

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from test_economics import saved

from eos_pv_helper import dashboard_view as view
from eos_pv_helper import economics as cost
from eos_pv_helper import ems_shadow as shadow
from eos_pv_helper.plan_actual import Actuals

AS_OF = datetime(2026, 11, 2, 12, tzinfo=UTC)


def hand_runner(data, *, baseline, load_scale):
    """Only a hand-computed test oracle for unity-efficiency zero-PV fixtures."""
    count, seconds = data["control_slots"], data["interval_seconds"]
    soc, capacity = data["battery"]["initial_soc_percentage"], data["battery"]["capacity_wh"]
    slots = []
    start = shadow.stamp(data["start_utc"])
    for i in range(count):
        load = data["series"]["total_load"][i]
        discharge = min(load, max(0, (soc - 10) / 100 * capacity)) if baseline else 0
        end_soc = soc - discharge / capacity * 100
        price = data["series"]["electricity_price_per_wh"][i]
        slots.append({"start_utc": (start + timedelta(seconds=i*seconds)).isoformat(),
            "interval_seconds": seconds, "grid_import_wh": load - discharge, "grid_export_wh": 0,
            "pv_wh": 0, "load_wh": load, "battery_charge_dc_wh": 0, "battery_discharge_dc_wh": discharge,
            "soc_start_percent": soc, "soc_end_percent": end_soc, "grid_cost_eur": (load-discharge)*price,
            "feed_in_revenue_eur": 0, "wear_eur": 0, "losses_wh": 0})
        soc = end_soc
    return {"slots": slots, "result": data["expected"], "end_soc_percent": soc,
            "end_usable_ac_wh": (soc - 10) / 100 * capacity, "engine": {"synthetic_oracle": True}}


def fixture(*, start=None, runner=hand_runner, count=24):
    original = saved(count=count)
    original["synthetic_only"] = True
    if start:
        original["start_solution_datetime"] = start.isoformat()
    data = cost.project(original)
    reference = runner(data, baseline=True, load_scale=1)
    points = {data["start_utc"]: data["battery"]["initial_soc_percentage"]}
    energy, tariffs, costs = [], [], []
    for r in reference["slots"]:
        left = shadow.stamp(r["start_utc"])
        right = left + timedelta(seconds=r["interval_seconds"])
        identity = {"start_utc": left.isoformat(), "end_utc": right.isoformat()}
        energy.append({**identity, **{k: r[k] for k in shadow.ENERGY}, "pv_dc_wh": r["pv_wh"]})
        tariffs.append({**identity, "retail_eur_kwh": .3})
        costs.append({**identity, "grid_cost_eur": r["grid_cost_eur"]})
        points[right.isoformat()] = r["soc_end_percent"]
    export = {"schema_version": 1, "energy_kind": "measured_interval_wh", "synthetic_only": True,
        "origin": {"kind": "operator_meter_export", "source_artifact_sha256": "a" * 64,
            "pv_basis": "ac", "pv_dc_basis": "inverter_input_dc", "battery_basis": "dc_bus",
            "house_load_scope": "whole_site_including_loadpoints", "tariff_basis": "retail_final_eur_kwh",
            "cost_basis": "measured_grid_purchase_eur", "manufacturer_standard_mode_confirmed": True},
        "energy": energy, "tariffs": tariffs, "costs": costs,
        "soc": [{"at_utc": t, "percent": v} for t, v in sorted(points.items())]}
    return original, export


def context(original, export):
    actuals = Actuals(cost.canonical(export))
    conditions = {"actuals_sha256": actuals.sha, "model_parameters_sha256": shadow.model_parameters(cost.project(original)),
        "evidence_sha256": "b" * 64, "meter_boundaries_confirmed": True,
        "usable_capacity_confirmed": True, "standard_mode_confirmed": True}
    return actuals, conditions


def evaluate(original, export, *, conditions=None, runner=hand_runner):
    actuals, defaults = context(original, export)
    return shadow.evaluate(cost.canonical(original), {"admission": "original_file_model_only"}, actuals,
        defaults if conditions is None else conditions, as_of=AS_OF, runner=runner)


def test_three_scenarios_same_conditions_terminal_and_separate_cost_scopes():
    original, export = fixture()
    result = evaluate(original, export)
    assert result["status"] == "SYNTHETIC_COMPARABLE"
    assert result["actual_input_reference"]["summary"]["grid_import_wh"]["delta_kwh"] == pytest.approx(0)
    assert result["actual_input_reference"]["summary"]["battery_losses_wh"]["actual"] == pytest.approx(0)
    assert result["costs"]["A_metered_cost_eur"] == pytest.approx(6.03)
    assert result["costs"]["B_reference"]["grid_cost_eur"] == pytest.approx(6.03)
    assert result["costs"]["C_fixed_genetic"]["grid_cost_eur"] == pytest.approx(7.2)
    assert result["costs"]["A_model_valued"]["adjusted_cost_eur"] == pytest.approx(6.03)
    assert result["costs"]["A_model_valued"]["terminal_credit_eur"] == pytest.approx(0)
    assert result["costs"]["hypothetical_A_minus_C_eur"] == pytest.approx(0)
    assert result["costs"]["hypothetical_B_minus_C_eur"] == pytest.approx(0)
    assert result["realized_savings_eur"] is None


@pytest.mark.parametrize("missing", ["dc-pv", "soc", "initial-soc", "energy", "tariff", "mode", "boundary", "capacity", "evidence", "balance"])
def test_missing_and_unproven_data_never_become_validated_model_errors(missing):
    original, export = fixture()
    if missing == "dc-pv":
        export["origin"].pop("pv_dc_basis")
    elif missing == "soc":
        export["soc"].pop(3)
    elif missing == "initial-soc":
        export["soc"][0]["percent"] = 41
    elif missing == "energy":
        export["energy"].pop(2)
    elif missing == "tariff":
        export["tariffs"].pop(2)
    elif missing == "mode":
        export["origin"]["manufacturer_standard_mode_confirmed"] = False
    elif missing == "balance":
        export["energy"][4]["grid_import_wh"] += 51
    actuals, conditions = context(original, export)
    if missing == "boundary":
        conditions["meter_boundaries_confirmed"] = False
    if missing == "capacity":
        conditions["usable_capacity_confirmed"] = False
    if missing == "evidence":
        conditions["actuals_sha256"] = "c" * 64
    result = shadow.evaluate(cost.canonical(original), {}, actuals, conditions, as_of=AS_OF, runner=hand_runner)
    assert result["status"] == "NOT_COMPARABLE" and result["reasons"]
    assert "costs" not in result and "actual_input_reference" not in result
    assert result["forecast_replay"]["replay_verified"] is True


def test_forecast_error_is_not_reported_as_model_error():
    original, export = fixture()
    # Distinct actual load but physically consistent actual grid energy.
    for r in export["energy"][5:]:
        r["load_wh"] += 100
        r["grid_import_wh"] += 100
    for r in export["costs"][5:]:
        r["grid_cost_eur"] += .03
    result = evaluate(original, export)
    assert result["status"] == "SYNTHETIC_COMPARABLE"
    assert result["forecast_errors"]["total_load"]["delta_kwh"] == pytest.approx(-1.9)
    assert result["actual_input_reference"]["summary"]["grid_import_wh"]["delta_kwh"] == pytest.approx(0)
    assert result["measured"][5]["cost_counter_minus_energy_times_price_eur"] == pytest.approx(0)


def test_missing_metered_cost_is_not_relabelled_as_measured():
    original, export = fixture()
    export.pop("costs")
    result = evaluate(original, export)
    assert result["status"] == "SYNTHETIC_COMPARABLE"
    assert result["costs"]["A_metered_cost_eur"] is None
    assert result["costs"]["A_grid_purchase_calculated_eur"] == pytest.approx(6.03)


def test_fine_tariffs_are_not_averaged_using_actual_grid_weights():
    original, export = fixture(count=1)
    original = saved(count=24)  # Preserve valid original result/terminal curve.
    _, export = fixture()
    first = export["tariffs"].pop(0)
    mid = shadow.stamp(first["start_utc"]) + timedelta(minutes=30)
    export["tariffs"][:0] = [{**first, "end_utc": mid.isoformat()}, {**first, "start_utc": mid.isoformat(), "retail_eur_kwh": -.1}]
    result = evaluate(original, export)
    assert result["status"] == "NOT_COMPARABLE"
    assert "costs" not in result


def test_negative_final_price_is_never_surcharged_twice():
    original, export = fixture()
    for t in export["tariffs"]:
        t["retail_eur_kwh"] = -.2
    export.pop("costs")
    result = evaluate(original, export)
    assert result["costs"]["A_grid_purchase_calculated_eur"] == pytest.approx(-4.02)
    assert result["costs"]["C_fixed_genetic"]["grid_cost_eur"] == pytest.approx(-4.8)


def test_idempotent_cache_is_bound_to_actuals_conditions_code_and_corruption(tmp_path):
    tmp_path.chmod(0o700)
    original, export = fixture()
    actuals, conditions = context(original, export)
    entries = [{"raw": cost.canonical(original), "binding": {}}]
    first = shadow.batch(entries, actuals, conditions, tmp_path, as_of=AS_OF, runner=hand_runner)
    before = {p.name: p.stat().st_mtime_ns for p in (tmp_path / "records").iterdir()}
    def forbidden(*a, **k):
        pytest.fail("cache replayed the native engine")
    second = shadow.batch(entries, actuals, conditions, tmp_path, as_of=AS_OF, runner=forbidden)
    assert first == second
    assert before == {p.name: p.stat().st_mtime_ns for p in (tmp_path / "records").iterdir()}
    # Earlier watermark must never turn a cached historical run into a future measurement.
    early = shadow.batch(entries, actuals, conditions, tmp_path, as_of=shadow.stamp(original["start_solution_datetime"]), runner=forbidden)
    assert early["results"][0]["status"] == "NOT_COMPARABLE"
    conditions["meter_boundaries_confirmed"] = False
    changed = shadow.batch(entries, actuals, conditions, tmp_path, as_of=AS_OF, runner=hand_runner)
    assert changed["results"][0]["status"] == "NOT_COMPARABLE"
    assert len(list((tmp_path / "records").iterdir())) == 2
    path = tmp_path / "records" / next(iter(before))
    path.chmod(0o600)
    path.write_text('{}')
    with pytest.raises((KeyError, shadow.WorkerError)):
        shadow.batch(entries, actuals, context(original, export)[1], tmp_path, as_of=AS_OF, runner=forbidden)


def test_failed_native_run_is_retried_not_cached_as_zero(tmp_path):
    tmp_path.chmod(0o700)
    original, export = fixture()
    actuals, conditions = context(original, export)
    def failed(*a, **k):
        raise ImportError("synthetic missing engine")
    entries = [{"raw": cost.canonical(original), "binding": {}}]
    first = shadow.batch(entries, actuals, conditions, tmp_path, as_of=AS_OF, runner=failed)
    assert first["results"][0]["status"] == "NOT_COMPARABLE"
    assert not list((tmp_path / "records").iterdir())
    second = shadow.batch(entries, actuals, conditions, tmp_path, as_of=AS_OF, runner=hand_runner)
    assert second["results"][0]["status"] == "SYNTHETIC_COMPARABLE"


def test_thirty_day_disjoint_selection_no_overlapping_plan_double_count():
    results = []
    start = AS_OF - timedelta(days=30)
    for i in range(30):
        original, export = fixture(start=start+timedelta(days=i))
        results.append(evaluate(original, export))
    # An overlapping extra plan must not turn 720h into 744h.
    results.append(copy.deepcopy(results[10]))
    result = shadow.ranges(results, AS_OF)
    assert result["30"]["coverage_hours"] == 720
    assert result["7"]["coverage_hours"] == 168
    assert result["1"]["coverage_hours"] == 24
    assert result["30"]["synthetic_only"] is True
    assert result["30"]["continuous_shadow_proven"] is False
    del results[3]
    assert shadow.ranges(results, AS_OF)["30"]["hypothetical_B_minus_C_eur"] is None


def test_real_original_without_archive_is_not_authenticated_by_consistent_hashes():
    original, export = fixture()
    original.pop("synthetic_only")
    export.pop("synthetic_only")
    result = evaluate(original, export)
    assert result["status"] == "NOT_COMPARABLE"
    assert "historical_archive_binding_not_proven" in result["reasons"]


def test_dashboard_projection_drops_private_text_and_rejects_nonfinite(tmp_path):
    tmp_path.chmod(0o700)
    original, export = fixture()
    actuals, conditions = context(original, export)
    report = shadow.batch([{"raw": cost.canonical(original), "binding": {"private": "SECRET"}}], actuals,
                          conditions, tmp_path, as_of=AS_OF, runner=hand_runner)
    projection = view.project_shadow_report(report)
    assert "SECRET" not in json.dumps(projection)
    assert projection["results"][0]["grid_delta_kwh"] == pytest.approx(0)
    report["results"][0]["actual_grid_purchase_metered_eur"] = float("nan")
    with pytest.raises(ValueError):
        view.project_shadow_report(report)


def test_native_forward_calls_only_no_optimizer_or_io(monkeypatch):
    original, export = fixture()
    calls = []
    def spy(data, **kw):
        calls.append(kw)
        return hand_runner(data, **kw)
    import socket

    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network"))
    result = evaluate(original, export, runner=spy)
    assert result["status"] == "SYNTHETIC_COMPARABLE"
    assert calls == [{"baseline": False, "load_scale": 1}, {"baseline": True, "load_scale": 1},
                     {"baseline": True, "load_scale": 1}, {"baseline": False, "load_scale": 1}]


def test_dashboard_only_reads_report_and_preserves_last_good_on_bad_refresh(tmp_path, monkeypatch):
    from dashboard_fixture import make

    from eos_pv_helper import dashboard

    source = make(tmp_path / "source")
    output = tmp_path / "shadow"
    output.mkdir(mode=0o700)
    original, export = fixture()
    actuals, conditions = context(original, export)
    shadow.batch([{"raw": cost.canonical(original), "binding": {}}], actuals, conditions,
                 output, as_of=AS_OF, runner=hand_runner)
    def forbidden(*a, **k):
        pytest.fail("dashboard must never invoke simulation")
    monkeypatch.setattr(cost, "compare", forbidden)
    path = output / "report.json"
    html, valid = dashboard.render_refresh(source, shadow_file=path)
    assert valid and 'id="ems-shadow-panel"' in html
    data = json.loads(dashboard.DATA_PATTERN.search(html)[1])
    assert data["ems_shadow"]["results"][0]["status"] == "SYNTHETIC_COMPARABLE"
    path.write_text('{}')
    recovered, valid = dashboard.render_refresh(source, previous=html, shadow_file=path)
    assert not valid
    previous = json.loads(dashboard.DATA_PATTERN.search(recovered)[1])
    assert previous["update_error"] is True
    assert previous["ems_shadow"] == data["ems_shadow"]


def test_measured_counter_tariff_mismatch_is_not_hidden():
    original, export = fixture()
    export["costs"][5]["grid_cost_eur"] += .02
    result = evaluate(original, export)
    assert result["status"] == "NOT_COMPARABLE"
    assert "measured_cost_and_tariff_disagree" in result["reasons"]
    assert result["measured"][5]["cost_counter_minus_energy_times_price_eur"] == pytest.approx(.02)
    assert "costs" not in result


def test_stable_confirmed_mapping_allows_new_arrivals_but_changed_mapping_does_not():
    original, export = fixture()
    export["origin"]["measurement_mapping_sha256"] = "d" * 64
    _, conditions = context(original, export)
    conditions.pop("actuals_sha256")
    conditions["measurement_mapping_sha256"] = "d" * 64
    # Original artifact identity can change when the authoritative source adds data.
    export["origin"]["source_artifact_sha256"] = "e" * 64
    assert evaluate(original, export, conditions=conditions)["status"] == "SYNTHETIC_COMPARABLE"
    export["origin"]["measurement_mapping_sha256"] = "f" * 64
    result = evaluate(original, export, conditions=conditions)
    assert result["status"] == "NOT_COMPARABLE"
    assert "calibration_evidence_unbound" in result["reasons"]


def test_import_weighted_actual_cost_rate_is_not_used_to_price_hypothetical_strategy():
    original, export = fixture()
    export["tariffs"][0]["source_method"] = "derived_energy_weighted_cost"
    result = evaluate(original, export)
    assert result["actual_grid_purchase_calculated_eur"] == pytest.approx(6.03)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["reasons"] == ["import_weighted_tariff_not_strategy_price"]
    assert "costs" not in result

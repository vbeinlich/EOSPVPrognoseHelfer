"""Idempotent OFFLINE evaluation of existing archives, never an optimizer/collector.

All physics and accounting remain in economics/economics_native. Actual intervals
remain in plan_actual, prepared exports in energy_data, archive admission in the
existing replay worker. No service, schedule or device integration is installed.
"""

import argparse
import bisect
import copy
import fcntl
import importlib.metadata
import json
import math
import os
import re
import sys
from contextlib import chdir
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import economics as cost
from . import economics_native as native
from .plan_actual import ENERGY, Actuals, stamp
from .replay_worker_io import WorkerError, directory, read, sha, write

CONTRACT = "eos-pv-helper/ems-shadow-v1.2"
HASH = re.compile(r"[0-9a-f]{64}")
TOLERANCE_WH = 50  # Same strict historical hourly threshold; never relaxed.


def code_identity():
    names = ("ems_shadow", "economics", "economics_native", "plan_actual", "energy_data",
             "historical", "replay_worker", "replay_worker_io")
    dependencies = {}
    for name in ("numpy", "scipy", "pydantic"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "unavailable"
    try:
        import akkudoktoreos

        source = native.fingerprint(Path(akkudoktoreos.__path__[0]))
    except ImportError:
        source = "unavailable"
    return {"code": {n: sha(Path(__file__).with_name(n + ".py").read_bytes().replace(
        b"\r\n", b"\n")) for n in names}, "dependencies": dependencies,
        "eos_revision": native.EOS_REVISION, "expected_source": native.EXPECTED_SOURCE,
        "installed_source": source}


def model_parameters(data):
    battery = {k: v for k, v in data["battery"].items() if k != "initial_soc_percentage"}
    return cost.digest({"battery": battery, "inverter": data["inverter"]})


def metric(actual, simulated, *, unit="Wh"):
    delta = simulated - actual if actual is not None and simulated is not None else None
    return {"actual": actual, "simulated": simulated, "delta_simulated_minus_actual": delta,
            "delta_kwh": delta / 1000 if delta is not None and unit == "Wh" else None,
            "delta_percent": 100 * delta / abs(actual) if delta is not None and abs(actual) > 1e-9 else None,
            "unit": unit}


def measured_window(data, actuals, conditions):
    """Gate a whole original control horizon; no filling, price averaging or splitting."""
    reasons, rows = set(), []
    if actuals is None:
        return [], ["actuals_missing"]
    mapping_bound = (isinstance(actuals.mapping_sha, str) and HASH.fullmatch(actuals.mapping_sha)
                     and conditions.get("measurement_mapping_sha256") == actuals.mapping_sha)
    bound = ((conditions.get("actuals_sha256") == actuals.sha or mapping_bound)
             and conditions.get("model_parameters_sha256") == model_parameters(data)
             and isinstance(conditions.get("evidence_sha256"), str)
             and HASH.fullmatch(conditions["evidence_sha256"]))
    if not bound:
        reasons.add("calibration_evidence_unbound")
    for field in ("meter_boundaries_confirmed", "usable_capacity_confirmed", "standard_mode_confirmed"):
        if not bound or conditions.get(field) is not True:
            reasons.add(field + "_missing")
    if not actuals.standard:
        reasons.add("actual_operating_mode_unconfirmed")
    if not actuals.pv_dc:
        reasons.add("measured_native_dc_pv_missing")
    start = stamp(data["start_utc"])
    initial, _ = actuals.soc_at(start)
    if initial is None:
        reasons.add("initial_soc_missing_or_stale")
    elif not math.isclose(initial, data["battery"]["initial_soc_percentage"], abs_tol=.1):
        reasons.add("initial_soc_mismatch")
    for i in range(data["control_slots"]):
        left = start + timedelta(seconds=i * data["interval_seconds"])
        right = left + timedelta(seconds=data["interval_seconds"])
        values = {k: actuals.total(k, left, right) for k in (*ENERGY, "pv_dc_wh")}
        soc0, source0 = actuals.soc_at(left)
        soc1, source1 = actuals.soc_at(right)
        if any(v is None for v in values.values()):
            reasons.add("energy_coverage_or_meter_basis_missing")
        if soc0 is None or soc1 is None:
            reasons.add("soc_missing_or_stale")
        if any(v is not None and not data["battery"]["min_soc_percentage"] - .1 <= v
               <= data["battery"]["max_soc_percentage"] + .1 for v in (soc0, soc1)):
            reasons.add("observed_soc_outside_model_limits")
        grid_cash = actuals.cash_cost(left, right)
        metered_cash = actuals.measured_cash_cost(left, right)
        if grid_cash is None:
            reasons.add("final_retail_cost_coverage_missing")
        if metered_cash is not None and grid_cash is not None and abs(metered_cash-grid_cash) > .01:
            reasons.add("measured_cost_and_tariff_disagree")
        # Check every original subinterval, not just the aggregate horizon. DC
        # charge/discharge is mapped to AC with the explicitly bound inverter.
        original = actuals.window(actuals.energy, actuals.energy_starts, left, right)
        residuals = []
        for a, b, _ in original:
            v = {k: actuals.total(k, a, b) for k in ENERGY}
            if all(x is not None for x in v.values()):
                residual = (v["pv_wh"] + v["grid_import_wh"]
                    + v["battery_discharge_dc_wh"] * data["inverter"]["dc_to_ac_efficiency"]
                    - v["grid_export_wh"]
                    - v["battery_charge_dc_wh"] / data["inverter"]["ac_to_dc_efficiency"]
                    - v["load_wh"])
                residuals.append(residual)
                # Smaller original intervals get the same Wh/h budget, never a larger one.
                if abs(residual) > TOLERANCE_WH * (b - a).total_seconds() / 3600:
                    reasons.add("strict_energy_balance_failed")
        losses = None
        if (bound and conditions.get("usable_capacity_confirmed") is True
                and actuals.battery_dc and soc0 is not None and soc1 is not None
                and values["battery_charge_dc_wh"] is not None
                and values["battery_discharge_dc_wh"] is not None):
            losses = (values["battery_charge_dc_wh"] - values["battery_discharge_dc_wh"]
                      - data["battery"]["capacity_wh"] * (soc1 - soc0) / 100)
            if losses < -TOLERANCE_WH * data["interval_seconds"] / 3600:
                reasons.add("negative_inferred_battery_losses")
        rows.append({"start_utc": left.isoformat(), "end_utc": right.isoformat(),
                     "energy": values, "soc_start_percent": soc0, "soc_end_percent": soc1,
                     "soc_start_source": source0, "soc_end_source": source1,
                     "grid_cash_eur": grid_cash, "balance_residuals_wh": residuals,
                     "metered_grid_cash_eur": metered_cash,
                     "cost_counter_minus_energy_times_price_eur": metered_cash - grid_cash
                     if metered_cash is not None and grid_cash is not None else None,
                     "battery_losses_wh": losses, "losses_quality": "derived_dc_balance_with_confirmed_capacity"
                     if losses is not None else "NOT_COMPARABLE"})
    return rows, sorted(reasons)


def metrics_for(run, measured, data):
    rows = []
    for predicted, observed in zip(run["slots"], measured, strict=True):
        values = observed["energy"]
        # The native PV input is DC. AC PV is retained in the measured row, not
        # compared to a DC prediction. Charge/discharge are DC bus energies.
        pairs = {k: metric(values[k], predicted[k]) for k in ENERGY if k != "pv_wh"}
        pairs["pv_dc_wh"] = metric(values["pv_dc_wh"], predicted["pv_wh"])
        pairs["soc_end_percent"] = metric(observed["soc_end_percent"], predicted["soc_end_percent"], unit="percent")
        pairs["grid_cost_eur"] = metric(observed["grid_cash_eur"], predicted["grid_cost_eur"], unit="EUR")
        battery = data["battery"]
        losses = (predicted["battery_charge_dc_wh"] * (1 - battery["charging_efficiency"])
                  + predicted["battery_discharge_dc_wh"] * (1 / battery["discharging_efficiency"] - 1))
        pairs["battery_losses_wh"] = metric(observed["battery_losses_wh"], losses)
        rows.append({"start_utc": observed["start_utc"], "end_utc": observed["end_utc"], "metrics": pairs})
    summary = {}
    for key in rows[0]["metrics"] if rows else ():
        pairs = [r["metrics"][key] for r in rows]
        if all(p["actual"] is not None and p["simulated"] is not None for p in pairs):
            # SoC is a point, never an energy integral or sum of percentages.
            if key == "soc_end_percent":
                summary[key] = {"mae_percentage_points": sum(abs(p["delta_simulated_minus_actual"])
                                                           for p in pairs) / len(pairs)}
            else:
                summary[key] = metric(sum(p["actual"] for p in pairs), sum(p["simulated"] for p in pairs),
                                      unit=pairs[0]["unit"])
                summary[key]["mean_absolute_error"] = sum(abs(p["delta_simulated_minus_actual"]) for p in pairs) / len(pairs)
                summary[key]["max_absolute_error"] = max(abs(p["delta_simulated_minus_actual"]) for p in pairs)
    return {"rows": rows, "summary": summary}


def evaluate(raw, binding, actuals, conditions, *, as_of, runner=None, synthetic=False):
    """Native fixed-control forward passes; never GENETIC optimization."""
    runner = runner or native.simulate
    synthetic = synthetic or actuals is not None and actuals.synthetic
    result = {"source_solution_sha256": sha(raw), "binding": binding,
              "synthetic_only": synthetic, "status": "NOT_COMPARABLE", "reasons": [],
              "realized_savings_eur": None, "continuous_shadow_proven": False}
    try:
        if binding.get("admission") == "rejected_archive":
            result["reasons"] = [binding.get("reason", "archive_admission_failed")]
            return result
        data = cost.project(json.loads(raw))
        start = stamp(data["start_utc"])
        end = start + timedelta(seconds=data["control_slots"] * data["interval_seconds"])
        result.update(start_utc=start.isoformat(), end_utc=end.isoformat(),
                      model_parameters_sha256=model_parameters(data),
                      model_parameters={"battery": data["battery"], "inverter": data["inverter"]})
        if end > as_of:
            result["reasons"] = ["historical_interval_not_completed"]
            return result
        measured, reasons = measured_window(data, actuals, conditions)
        if binding.get("admission") != "committed_original_archive" and not synthetic:
            reasons.append("historical_archive_binding_not_proven")
        result["reasons"] = sorted(set(reasons))
        result["measured"] = measured
        # First reproduce the original result exactly. Failure blocks all savings.
        forecast = cost.compare(data, runner=runner)
        result["forecast_replay"] = forecast
        result["forecast_interpretation"] = "stored_forecasts_only_not_model_validation_or_realized_savings"
        if measured:
            result["actual_grid_purchase_calculated_eur"] = sum(r["grid_cash_eur"] for r in measured) if all(
                r["grid_cash_eur"] is not None for r in measured) else None
            result["actual_cost_quality"] = "measured_import_times_original_final_retail_price_not_metered_cost_counter"
            result["actual_grid_purchase_metered_eur"] = sum(r["metered_grid_cash_eur"] for r in measured) if all(
                r["metered_grid_cash_eur"] is not None for r in measured) else None
            result["hourly_costs"] = [{"start_utc": m["start_utc"], "end_utc": m["end_utc"],
                "A_metered_eur": m["metered_grid_cash_eur"], "A_import_times_final_price_eur": m["grid_cash_eur"],
                "B_original_forecast_eur": b["grid_cost_eur"], "C_original_forecast_eur": g["grid_cost_eur"],
                "interpretation": "forecast_scenario_deviation_not_model_error"}
                for m, b, g in zip(measured, forecast["slots"]["baseline"], forecast["slots"]["genetic"], strict=True)]
            # Only load is the same boundary in both contracts. DC PV can be
            # paired separately when actually measured; AC PV is never substituted.
            result["forecast_errors"] = {k: metric(
                sum(r["energy"][m] for r in measured), sum(data["series"][k][:len(measured)]))
                for k, m in (("total_load", "load_wh"), ("pv_forecast_wh", "pv_dc_wh"))
                if all(r["energy"][m] is not None for r in measured)}
        if reasons:
            return result
        actual_input = copy.deepcopy(data)
        actual_input["series"]["pv_forecast_wh"] = [r["energy"]["pv_dc_wh"] for r in measured]
        actual_input["series"]["total_load"] = [r["energy"]["load_wh"] for r in measured]
        # One original final retail price must cover each model slot. A weighted
        # price using actual import would bias hypothetical strategies.
        prices = []
        for r in measured:
            a, b = stamp(r["start_utc"]), stamp(r["end_utc"])
            i = bisect.bisect_right(actuals.tariff_starts, a) - 1
            if i < 0 or actuals.tariffs[i][1] < b or "retail_eur_kwh" not in actuals.tariffs[i][2]:
                result["reasons"] = ["retail_tariff_finer_than_native_slot"]
                return result
            if actuals.tariffs[i][:2] in actuals.import_weighted_tariffs:
                result["reasons"] = ["import_weighted_tariff_not_strategy_price"]
                return result
            prices.append(actuals.tariffs[i][2]["retail_eur_kwh"] / 1000)
        actual_input["series"]["electricity_price_per_wh"] = prices
        # Fixed archived controls on actual inputs are a hindsight sensitivity,
        # not an optimization using retrospective forecasts.
        reference = runner(actual_input, baseline=True, load_scale=1)
        genetic = runner(actual_input, baseline=False, load_scale=1)
        ref_account, gen_account = (cost.account(r, data["terminal_curve"]) for r in (reference, genetic))
        end_soc = measured[-1]["soc_end_percent"]
        usable_ac = max(0, (end_soc - data["battery"]["min_soc_percentage"]) / 100
                        * data["battery"]["capacity_wh"] * data["battery"]["discharging_efficiency"]
                        * data["inverter"]["dc_to_ac_efficiency"])
        actual_terminal = cost.terminal_value(data["terminal_curve"], usable_ac)
        actual_account = None
        if (conditions.get("feed_in_tariff_confirmed") is True
                or all(r["energy"]["grid_export_wh"] == 0 for r in measured)):
            actual_slots = [{"grid_cost_eur": r["metered_grid_cash_eur"]
                if r["metered_grid_cash_eur"] is not None else r["grid_cash_eur"],
                "feed_in_revenue_eur": r["energy"]["grid_export_wh"] * data["series"]["feed_in_tariff_per_wh"][i],
                "wear_eur": r["energy"]["battery_discharge_dc_wh"] * data["battery"]["levelized_cost_of_storage_kwh"] / 1000,
                "grid_import_wh": r["energy"]["grid_import_wh"], "grid_export_wh": r["energy"]["grid_export_wh"],
                "losses_wh": r["battery_losses_wh"]} for i, r in enumerate(measured)]
            actual_account = cost.account({"slots": actual_slots, "end_soc_percent": end_soc,
                "end_usable_ac_wh": usable_ac}, data["terminal_curve"])
            actual_account["derived_battery_losses_kwh"] = actual_account.pop("losses_kwh")
            actual_account["valuation_quality"] = "measured_flows_with_model_wear_and_saved_terminal_curve_not_measured_total_cost"
        result["actual_input_reference"] = metrics_for(reference, measured, data)
        result["actual_input_genetic"] = metrics_for(genetic, measured, data)
        result["costs"] = {"A_grid_purchase_calculated_eur": result["actual_grid_purchase_calculated_eur"],
                           "A_metered_cost_eur": result["actual_grid_purchase_metered_eur"],
                           "A_model_valued": actual_account, "A_terminal_credit_eur": actual_terminal,
                           "B_reference": ref_account, "C_fixed_genetic": gen_account,
                           "hypothetical_B_minus_C_eur": ref_account["adjusted_cost_eur"] - gen_account["adjusted_cost_eur"],
                           "scope": "independent_saved_horizon_same_initial_state_and_saved_terminal_curve",
                           "A_total_economic_cost_comparable": actual_account is not None,
                           "hypothetical_A_minus_C_eur": actual_account["adjusted_cost_eur"] - gen_account["adjusted_cost_eur"]
                           if actual_account is not None else None,
                           "feed_in_tariff_scope": "saved_plan_operator_confirmed"
                           if conditions.get("feed_in_tariff_confirmed") is True
                           else "saved_plan_not_confirmed_measured_revenue"}
        result["status"] = "SYNTHETIC_COMPARABLE" if synthetic else "COMPARABLE"
    except Exception as exc:
        # No raw exception/config text in persisted/public views. Retry native
        # failures on the next invocation; never cache a fake zero saving.
        result["reasons"] = ["native_replay_or_input_validation_failed"]
        result["failure_type"] = type(exc).__name__
        result.pop("costs", None)
    return result


def ranges(results, as_of):
    """Maximum covered, disjoint WHOLE horizons; no slot slicing or tail credit reuse."""
    report = {}
    for days in (1, 7, 30):
        start = as_of - timedelta(days=days)
        candidates = [r for r in results if r.get("start_utc") and r.get("end_utc")
                      and stamp(r["start_utc"]) >= start and stamp(r["end_utc"]) <= as_of
                      and r["status"] in ("COMPARABLE", "SYNTHETIC_COMPARABLE")]
        candidates.sort(key=lambda r: (r["end_utc"], r["start_utc"], r["source_solution_sha256"]))
        if any(r["status"] == "COMPARABLE" for r in candidates):
            candidates = [r for r in candidates if r["status"] == "COMPARABLE"]
        ends, dp = [stamp(r["end_utc"]) for r in candidates], [(0, [])]
        for i, row in enumerate(candidates):
            left, right = stamp(row["start_utc"]), stamp(row["end_utc"])
            previous = bisect.bisect_right(ends, left, hi=i)
            chosen = (dp[previous][0] + (right-left).total_seconds(), dp[previous][1] + [row])
            dp.append(chosen if chosen[0] > dp[-1][0] else dp[-1])
        seconds, selected = dp[-1]
        full = seconds == days * 86400
        report[str(days)] = {"status": "COMPLETE" if full else "NOT_COMPARABLE",
            "start_utc": start.isoformat(), "end_utc": as_of.isoformat(),
            "coverage_hours": seconds / 3600, "expected_hours": days * 24,
            "selected_source_sha256": [r["source_solution_sha256"] for r in selected],
            "synthetic_only": bool(selected) and all(r["synthetic_only"] for r in selected),
            "independent_horizons": True, "continuous_shadow_proven": False,
            "actual_grid_purchase_calculated_eur": sum(r["costs"]["A_grid_purchase_calculated_eur"]
                for r in selected) if full else None,
            "hypothetical_B_minus_C_eur": sum(r["costs"]["hypothetical_B_minus_C_eur"]
                for r in selected) if full else None,
            "hypothetical_A_minus_C_eur": sum(r["costs"]["hypothetical_A_minus_C_eur"] for r in selected)
            if full and all(r["costs"]["hypothetical_A_minus_C_eur"] is not None for r in selected) else None,
            "realized_savings_eur": None}
    return report


def batch(entries, actuals, conditions, output, *, as_of, runner=None, prepared_audit=None):
    """Append-only content cache plus atomic report. Single writer, no source writes."""
    output = directory(output)
    if output.stat().st_mode & 0o077:
        raise WorkerError("workspace_not_private")
    if (output / ".shadow.lock").is_symlink():
        raise WorkerError("unsafe_destination")
    with (output / ".shadow.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        records = output / "records"
        records.mkdir(mode=0o700, exist_ok=True)
        directory(records)
        identity = code_identity()
        results = []
        for entry in entries:
            raw, binding, synthetic = entry["raw"], entry["binding"], entry.get("synthetic", False)
            key = cost.digest({"solution": sha(raw), "binding": binding, "synthetic": synthetic,
                "actuals": actuals.sha if actuals else None, "conditions": conditions,
                "prepared_audit": prepared_audit, "implementation": identity})
            path = records / (key + ".json")
            if path.exists() or path.is_symlink():
                sealed = json.loads(read(path, 64_000_000))
                result = sealed["result"]
                if sealed.get("key") != key or sealed.get("result_sha256") != cost.digest(result):
                    raise WorkerError("shadow_cache_corrupt")
                if result.get("end_utc") and stamp(result["end_utc"]) > as_of:
                    result = {**{k: result[k] for k in ("source_solution_sha256", "binding", "synthetic_only", "start_utc", "end_utc")},
                              "status": "NOT_COMPARABLE", "reasons": ["historical_interval_not_completed"],
                              "realized_savings_eur": None, "continuous_shadow_proven": False}
            else:
                result = evaluate(raw, binding, actuals, conditions, as_of=as_of,
                                  runner=runner, synthetic=synthetic)
                if ("native_replay_or_input_validation_failed" not in result["reasons"]
                        and "historical_interval_not_completed" not in result["reasons"]):
                    write(path, cost.canonical({"key": key, "result_sha256": cost.digest(result),
                                               "result": result}), immutable=True)
            results.append(result)
        report = {"contract": CONTRACT, "read_only": True, "optimizer_invoked": False,
            "devices_commanded": False, "as_of_utc": as_of.isoformat(),
            "implementation": identity, "actuals_sha256": actuals.sha if actuals else None,
            "prepared_audit": prepared_audit, "results": results, "ranges": ranges(results, as_of),
            "realized_savings_eur": None, "annual_return": None,
            "luox": {"contract": "(net_market + 0.03 * abs(net_market) + fixed_net) * 1.19",
                     "retail_final_prices_modified": False,
                     "contract_validation": "use_existing_tariff_audit_with_original_net_components"}}
        write(output / "report.json", cost.canonical(report))
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--source", help="Existing local helper archive snapshot, read only")
    inputs.add_argument("--solution", action="append", help="Original local response, model-only provenance")
    measurements = parser.add_mutually_exclusive_group()
    measurements.add_argument("--actuals", help="Existing plan_actual measured-interval contract")
    measurements.add_argument("--prepared", help="Existing PR30 prepared.json; strict adapter gate retained")
    parser.add_argument("--conditions", help="Private SHA-bound calibration evidence JSON")
    parser.add_argument("--output", required=True, help="Existing separate 0700 private directory")
    parser.add_argument("--as-of", required=True, help="Explicit UTC watermark; no moving replay inputs")
    args = parser.parse_args(argv)
    try:
        from .replay_worker import object_json, snapshot
        from .replay_worker_job import deny_external_actions

        # Same existing replay child audit guard, installed before native imports.
        sys.addaudithook(deny_external_actions)
        as_of = stamp(args.as_of)
        if as_of > datetime.now(UTC):
            raise WorkerError("future_watermark")
        output = directory(args.output).resolve(strict=True)
        source = directory(args.source).resolve(strict=True) if args.source else None
        paths = [Path(p).resolve(strict=True) for p in (args.solution or [])]
        paths += [Path(p).resolve(strict=True) for p in (args.actuals, args.prepared, args.conditions) if p]
        if (source and (source == output or source in output.parents or output in source.parents)
                or any(output == p or output in p.parents for p in paths)):
            raise WorkerError("source_workspace_overlap")
        conditions = object_json(read(Path(args.conditions))) if args.conditions else {}
        actuals, audit = None, None
        if args.actuals:
            actuals = Actuals(read(Path(args.actuals)), now=as_of)
        if args.prepared:
            from .energy_data import as_actuals, verify_prepared

            prepared = object_json(read(Path(args.prepared), 64_000_000))
            verify_prepared(prepared)
            audit = {"source_sha256": sha(read(Path(args.prepared), 64_000_000)), **prepared["audit"]}
            if audit.get("status") == "passed":
                actuals = Actuals(cost.canonical(as_actuals(prepared)), now=as_of)
        entries = []
        if source:
            state = object_json(read(source / "sync-state.json", 8_000_000))
            for version, claim in sorted(state.get("events", {}).items()):
                if claim.get("status") != "succeeded":
                    continue
                try:
                    raw, binding = snapshot(source, version, as_of)
                except WorkerError as exc:
                    # Visible rejection; no invented original or silent omission.
                    entries.append({"raw": b"{}", "binding": {"event_version": version,
                                    "admission": "rejected_archive", "reason": str(exc)}})
                    continue
                entries.append({"raw": raw, "binding": binding})
        else:
            for p in args.solution:
                raw = read(Path(p), 8_000_000)
                entries.append({"raw": raw, "binding": {"admission": "original_file_model_only"},
                                "synthetic": object_json(raw).get("synthetic_only") is True})
        if not entries or len(entries) > 4096:
            raise WorkerError("no_inputs_or_budget_exceeded")
        runtime = output / "native-runtime"
        runtime.mkdir(mode=0o700, exist_ok=True)
        directory(runtime)
        if runtime.stat().st_mode & 0o077:
            raise WorkerError("workspace_not_private")
        config = runtime / "EOS.config.json"
        if not config.exists():
            write(config, b"{}", immutable=True)
        else:
            read(config, 8192)
        previous_environment = {k: os.environ.get(k) for k in ("EOS_DIR", "EOS_CONFIG_DIR")}
        try:
            os.environ.update(EOS_DIR=str(runtime), EOS_CONFIG_DIR=str(runtime))
            with chdir(runtime):
                report = batch(entries, actuals, conditions, output, as_of=as_of, prepared_audit=audit)
        finally:
            for key, value in previous_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        print(json.dumps({"evaluated": len(report["results"]), "comparable": sum(
            r["status"] == "COMPARABLE" for r in report["results"]), "ranges": report["ranges"]}))
        return 0 if all(r["status"] == "COMPARABLE" for r in report["results"]) else 2
    except Exception:
        print("Offline shadow evaluation failed; original inputs unchanged.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

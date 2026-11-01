"""Sanitized provenance for the EXISTING event archive; no config dumps or IO."""

import hashlib
import json
import math
import re


class ContextError(ValueError):
    pass


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def numeric(value):
    return value if (not isinstance(value, bool) and isinstance(value, (int, float))
                     and math.isfinite(value)) else None


def observed_options(settings):
    """Already-read settings: observation, NOT proof of an atomically frozen solver config."""
    load, optimization = settings.get("load", {}), settings.get("optimization", {})
    provider = load.get("provider")
    if provider not in ("LoadAkkudoktor", "LoadAkkudoktorAdjusted", "LoadImport"):
        provider = None
    g = optimization.get("genetic", {})
    result = {"scope": "cached_settings_read_at_sync_start_not_atomic_solver_options",
              "load_provider": provider,
              "annual_load_kwh": numeric(load.get("loadakkudoktor", {}).get("loadakkudoktor_year_energy_kwh")),
              "prediction_hours": numeric(settings.get("prediction", {}).get("hours")),
              "genetic_options": {k: numeric(g[k]) for k in (
                  "interval_sec", "horizon_hours", "tail_horizon_hours", "individuals", "generations",
                  "seed", "terminal_value_window_hours", "measurement_max_age_seconds") if k in g}}
    mode = g.get("terminal_value_mode")
    result["terminal_value_mode"] = mode if mode in ("AUTO", "FIXED") else None
    return result


def solution_inputs(solution):
    """Exact returned inputs remain in original solution bytes, without making up missing fields."""
    p = solution.get("parameters") or {}
    ems, battery, inverter = p.get("ems") or {}, p.get("pv_battery") or {}, p.get("inverter") or {}
    series = {}
    for key in ("total_load", "pv_forecast_wh", "electricity_price_per_wh", "feed_in_tariff_per_wh"):
        values = ems.get(key)
        if isinstance(values, list) and values and all(numeric(v) is not None for v in values):
            series[key] = {"sha256": canonical_sha(values), "slots": len(values)}
    result = {"scope": "original_returned_solution_parameters",
            "parameters_sha256": canonical_sha(p) if p else None, "series": series,
            "battery": {k: numeric(battery.get(k)) for k in ("capacity_wh", "initial_soc_percentage",
                "min_soc_percentage", "max_soc_percentage", "charging_efficiency", "discharging_efficiency",
                "max_charge_power_w", "levelized_cost_of_storage_kwh")},
            "inverter": {k: numeric(inverter.get(k)) for k in ("ac_to_dc_efficiency", "dc_to_ac_efficiency",
                "max_power_wh", "max_ac_charge_power_w")},
            "annual_load_exact_binding": "not_reported_by_solution",
            "optimizer_options_exact_binding": "not_reported_by_solution"}
    result["selected_model_inputs_present"] = (len(series) == 4
        and all(v is not None for v in result["battery"].values())
        and all(v is not None for v in result["inverter"].values()))
    return result


def verify_producer(producer, solution):
    """Optional extension; legacy evidence remains legacy, never reconstructed."""
    if not isinstance(producer, dict) or "observed_options" not in producer:
        return {"status": "not_available", "exact_solver_options_proven": False}
    if (canonical_sha(producer["observed_options"]) != producer.get("observed_options_sha256")
            or solution_inputs(solution) != producer.get("solution_inputs")
            or not re.fullmatch("[0-9a-f]{64}", producer.get("dispatched_request_sha256") or "")):
        raise ContextError("Event context hash or original solution binding differs")
    return {"status": "consistent_observation_and_returned_inputs", "exact_solver_options_proven": False,
            "returned_model_inputs_present": producer["solution_inputs"]["selected_model_inputs_present"],
            "annual_load_exact_binding": "not_reported_by_solution"}

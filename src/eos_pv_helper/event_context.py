"""Safe observation builder; validation lives only in the standalone historical engine."""

from .historical import ForecastError as ContextError
from .historical import canonical_sha, numeric, solution_inputs, verify_producer

__all__ = ["ContextError", "canonical_sha", "solution_inputs", "verify_producer", "observed_options"]


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

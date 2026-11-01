"""Offline plan-versus-measurement diagnostics; no acquisition, inference or control.

Input energies must already be measured interval integrals. Neither W samples,
resetting counters nor dry-run permissions are turned into measured energy.
"""

import bisect
import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta

ENERGY = ("pv_wh", "load_wh", "grid_import_wh", "grid_export_wh",
          "battery_charge_dc_wh", "battery_discharge_dc_wh")
KINDS = {"evcc_history_export", "homeassistant_statistics_export", "e3dc_meter_export",
         "operator_meter_export"}


class ActualsError(ValueError):
    pass


def stamp(value):
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.utcoffset() is None:
            raise ValueError()
        return d.astimezone(UTC)
    except (AttributeError, ValueError, TypeError):
        raise ActualsError("Measured timestamp must have an explicit timezone") from None


def number(value, *, nonnegative=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            or nonnegative and value < 0):
        raise ActualsError("Measured value is missing, nonfinite or has invalid units/sign")
    return value


class Actuals:
    def __init__(self, raw, *, now=None):
        now = now or datetime.now(UTC)
        if not isinstance(raw, bytes) or len(raw) > 8_000_000:
            raise ActualsError("Measured export missing or oversized")
        try:
            data = json.loads(raw)
            origin = data["origin"]
            if (type(data["schema_version"]) is not int or data["schema_version"] != 1
                    or data["energy_kind"] != "measured_interval_wh"
                    or origin["kind"] not in KINDS
                    or not re.fullmatch("[0-9a-f]{64}", origin["source_artifact_sha256"])):
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ActualsError("Invalid measured export contract or provenance") from None
        self.sha = hashlib.sha256(raw).hexdigest()
        self.source_sha = origin["source_artifact_sha256"]
        self.kind = origin["kind"]
        self.house_scope = origin.get("house_load_scope") == "whole_site_including_loadpoints"
        self.pv_ac = origin.get("pv_basis") == "ac"
        self.battery_dc = origin.get("battery_basis") == "dc_bus"
        self.retail = origin.get("tariff_basis") == "retail_final_eur_kwh"
        self.standard = origin.get("manufacturer_standard_mode_confirmed") is True
        self.energy = self.intervals(data.get("energy", []), ENERGY, nonnegative=True)
        self.tariffs = self.intervals(data.get("tariffs", []), ("retail_eur_kwh",), nonnegative=False)
        self.energy_starts = [r[0] for r in self.energy]
        self.tariff_starts = [r[0] for r in self.tariffs]
        points = data.get("soc", [])
        if not isinstance(points, list) or len(points) > 30000:
            raise ActualsError("Invalid or oversized measured SoC series")
        try:
            self.soc = sorted((stamp(r["at_utc"]), number(r["percent"])) for r in points)
        except (KeyError, TypeError):
            raise ActualsError("Invalid measured SoC point") from None
        if any(not 0 <= v <= 100 for _, v in self.soc) or len({t for t, _ in self.soc}) != len(self.soc):
            raise ActualsError("Invalid or duplicate measured SoC")
        self.soc_times = [p[0] for p in self.soc]
        if (any(r[1] > now for r in self.energy) or any(t > now for t in self.soc_times)):
            raise ActualsError("Future values cannot be accepted as completed measurements")

    @staticmethod
    def intervals(rows, keys, *, nonnegative):
        if not isinstance(rows, list) or len(rows) > 30000:
            raise ActualsError("Invalid or oversized measured interval series")
        parsed = []
        for row in rows:
            if not isinstance(row, dict):
                raise ActualsError("Measured interval must be an object")
            left, right = stamp(row.get("start_utc")), stamp(row.get("end_utc"))
            if not left < right or right-left > timedelta(days=1):
                raise ActualsError("Invalid measured interval duration")
            values = {k: number(row[k], nonnegative=nonnegative) for k in keys
                      if row.get(k) is not None}
            parsed.append((left, right, values))
        parsed.sort(key=lambda r: r[0])
        if any(b[0] < a[1] for a, b in zip(parsed, parsed[1:])):
            raise ActualsError("Measured intervals overlap or are duplicated")
        return parsed

    @staticmethod
    def window(rows, starts, start, end):
        # No proportional split of a coarse measurement across finer plan slots.
        i = max(0, bisect.bisect_right(starts, start)-1)
        selected = []
        while i < len(rows) and rows[i][0] < end:
            row = rows[i]
            if row[1] > start:
                selected.append(row)
            i += 1
        if (not selected or selected[0][0] != start or selected[-1][1] != end
                or any(a[1] != b[0] for a, b in zip(selected, selected[1:]))):
            return []
        return selected

    def total(self, key, start, end):
        if ((key == "pv_wh" and not self.pv_ac) or (key == "load_wh" and not self.house_scope)
                or (key.startswith("battery_") and not self.battery_dc)):
            return None
        rows = self.window(self.energy, self.energy_starts, start, end)
        if not rows or any(key not in r[2] for r in rows):
            return None
        return sum(r[2][key] for r in rows)

    def cash_cost(self, start, end):
        if not self.retail:
            return None
        rows = self.window(self.energy, self.energy_starts, start, end)
        if not rows or any("grid_import_wh" not in r[2] for r in rows):
            return None
        total = 0
        for left, right, values in rows:
            # One confirmed final price must cover the entire measured energy interval.
            i = bisect.bisect_right(self.tariff_starts, left)-1
            if i < 0 or self.tariffs[i][1] < right or "retail_eur_kwh" not in self.tariffs[i][2]:
                return None
            total += values["grid_import_wh"]/1000 * self.tariffs[i][2]["retail_eur_kwh"]
        return total

    def soc_at(self, at, max_age_seconds=60):
        i = bisect.bisect_right(self.soc_times, at)-1
        if i < 0:
            return None, None
        source, value = self.soc[i]
        age = (at-source).total_seconds()
        return (value, {"source_at_utc": source.isoformat(), "age_seconds": age}) if age <= max_age_seconds else (None, None)


def analyze(data, comparison, actuals):
    """Compare known quantities only. Dry-run deviations are NOT control/model failure proof."""
    from .economics import digest

    if comparison.get("status") != "calculated" or comparison.get("input_sha256") != digest(data):
        return {"status": "not_calculable", "message": "Nicht berechenbar: ursprüngliche Planwiedergabe fehlt oder passt nicht.",
                "realized_savings_eur": None}
    rows = []
    predictions = comparison["slots"]["genetic"]
    for i, prediction in enumerate(predictions):
        start = stamp(prediction["start_utc"])
        end = start+timedelta(seconds=prediction["interval_seconds"])
        quantities = {}
        for key in ENERGY:
            expected, actual = prediction.get(key), actuals.total(key, start, end)
            quantities[key] = {"predicted": expected, "actual": actual,
                "baseline_predicted": comparison["slots"]["baseline"][i].get(key),
                "delta_actual_minus_plan": actual-expected if actual is not None and expected is not None else None,
                "unit": "Wh"}
        actual_soc, source = actuals.soc_at(end)
        quantities["soc_end_percent"] = {"predicted": prediction["soc_end_percent"], "actual": actual_soc,
            "delta_actual_minus_plan": actual_soc-prediction["soc_end_percent"] if actual_soc is not None else None,
            "unit": "percent", "delta_unit": "percentage_points", "source": source}
        actual_cash = actuals.cash_cost(start, end)
        quantities["grid_cost_eur"] = {"predicted": prediction["grid_cost_eur"], "actual": actual_cash,
            "delta_actual_minus_plan": actual_cash-prediction["grid_cost_eur"] if actual_cash is not None else None,
            "unit": "EUR"}
        rows.append({"start_utc": start.isoformat(), "end_utc": end.isoformat(), "metrics": quantities})
    summary = {}
    for key in (*ENERGY, "soc_end_percent", "grid_cost_eur"):
        pairs = [r["metrics"][key] for r in rows if r["metrics"][key]["delta_actual_minus_plan"] is not None]
        summary[key] = {"paired_slots": len(pairs), "total_slots": len(rows),
            "mean_absolute_error": sum(abs(p["delta_actual_minus_plan"]) for p in pairs)/len(pairs) if pairs else None,
            "bias_actual_minus_plan": sum(p["delta_actual_minus_plan"] for p in pairs)/len(pairs) if pairs else None}
    cash = [r["metrics"]["grid_cost_eur"]["actual"] for r in rows]
    full = bool(rows) and all(v is not None for v in cash)
    return {"status": "available" if any(s["paired_slots"] for s in summary.values()) else "not_calculable",
            "message": "Plan-Ist-Diagnose; Dry-Run-Freigaben sind kein Ausführungsnachweis.",
            "actuals_sha256": actuals.sha, "source_artifact_sha256": actuals.source_sha,
            "source_kind": actuals.kind, "historical_authenticity_confirmed": False,
            "baseline_mode_operator_confirmed": actuals.standard,
            "reference_model_calibration": "not_proven_forecast_and_operating_mode_errors_not_separated",
            "interpretation": {"pv_wh": "forecast_error", "load_wh": "forecast_error",
                "grid_and_battery": "dry_run_scenario_deviation_not_attributable_model_error"},
            "actual_grid_cash_cost_eur": sum(cash) if full else None,
            "cash_coverage_complete": full, "summary": summary, "rows": rows,
            "realized_savings_eur": None,
            "realized_savings_status": "not_proven_no_confirmed_execution_or_validated_counterfactual",
            "cost_scope": "measured_grid_purchase_only_no_wear_terminal_value_or_fixed_fees"}

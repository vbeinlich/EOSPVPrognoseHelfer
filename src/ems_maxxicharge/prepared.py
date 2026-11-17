"""Admission of shared prepared measurements; simulator physics stays unchanged."""

import copy
import csv
import io
import math

from eos_pv_helper.energy_data import REQUIRED, EnergyDataError, verify_prepared

from .config import BatteryConfig, SimulationError, construct, number
from .history import ENERGY, fit_efficiencies, import_csv
from .inputs import digest, validate


def from_prepared(source, context):
    try:
        checked = verify_prepared(source)
        rows = checked["rows"]
        provisional_reasons = []
        if checked["audit"]["status"] != "passed":
            if (context.get("provisional_measurements_acknowledged") is not True
                    or context.get("historical_reference") is True):
                raise SimulationError("Incomplete/imbalanced measurements require a separate provisional mode")
            # Never admit missing energies/prices, partial mean-power coverage,
            # future intervals or an unknown initial SOC through this opt-in.
            allowed = {"missing:soc_start_percent", "missing:soc_end_percent", "site_balance_exceeds_tolerance"}
            if (any(r.get(k) is None for r in rows for k in REQUIRED)
                    or rows[0].get("soc_start_percent") is None
                    or any(issue not in allowed for r in rows for issue in r["issues"])):
                raise SimulationError("Provisional mode cannot fill missing energy, tariff or initial SOC")
            bound = number(context.get("provisional_max_site_balance_error_wh", 50),
                           "explicit provisional balance limit", 0, 500)
            if max(abs(r["site_balance_error_wh"]) for r in rows) > bound:
                raise SimulationError("Original site imbalance exceeds explicit provisional limit")
            provisional_reasons = sorted({issue for r in rows for issue in r["issues"]})
        battery = construct(BatteryConfig, context.get("e3dc"))
        battery = {**battery.__dict__, "initial_soc_percent": rows[0]["soc_start_percent"]}
        inputs = [{k: r[k] for k in ("start_utc", "end_utc", "load_wh", "base_pv_wh",
                                    "import_eur_kwh", "export_eur_kwh")} for r in rows]
        observed = [{**r, "battery_charge_ac_wh": r["battery_charge_wh"],
                     "battery_discharge_ac_wh": r["battery_discharge_wh"]} for r in rows]
        provisional = any("derived_power_left_hold" in q["status"] for r in rows for q in r["quality"].values())
        interval_means = any("derived_interval_mean_power" in q["status"] for r in rows for q in r["quality"].values())
        if provisional and context.get("provisional_simulation_acknowledged") is not True:
            raise SimulationError("Power-derived inputs require explicit provisional SIM acknowledgement")
        if context.get("historical_reference") is True:
            # Preserve all existing 120-hour, SOC, tariff and reference-total gates.
            fields = ["start_utc", "end_utc", *ENERGY, "import_eur_kwh", "export_eur_kwh",
                      "soc_start_percent", "soc_end_percent", "soc_start_at_utc", "soc_end_at_utc"]
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows({k: r[k] for k in fields} for r in rows)
            settings = {**context, "columns": {}, "units": dict.fromkeys(ENERGY, "Wh"),
                        "delimiter": ",", "decimal_separator": ".", "battery_basis": "ac_bus",
                        "energy_kind": "measured_interval_integrals", "data_kind": checked["data_kind"]}
            data = import_csv(stream.getvalue().encode(), settings)
        else:
            valid_soc = [r for r in observed if r["soc_start_percent"] is not None and r["soc_end_percent"] is not None]
            fit = fit_efficiencies(valid_soc, battery["capacity_wh"])
            # Generic future/backtest windows are not November regression admission.
            audit = {"status": "warnings", "historical_acceptance_passed": False,
                     "original_hours": len(rows), "source_kind": checked["data_kind"],
                     "soc_audit": {"usable_intervals": len(valid_soc),
                         "missing_or_stale_start_points": sum(r["soc_start_percent"] is None for r in rows),
                         "missing_or_stale_end_points": sum(r["soc_end_percent"] is None for r in rows),
                         "stale_points_replaced_or_interpolated": False},
                     "site_balance_audit": {"strict_tolerance_wh": checked["mapping"].get("site_balance_tolerance_wh", 50),
                         "failed_intervals": checked["audit"]["site_balance_failed_intervals"],
                         "max_abs_error_wh": max(abs(r["site_balance_error_wh"]) for r in rows),
                         "sum_error_wh": math.fsum(r["site_balance_error_wh"] for r in rows)},
                     "reference_totals": {k: math.fsum(r[k] for r in rows) for k in (
                         "load_wh", "base_pv_wh", "grid_import_wh", "grid_export_wh", "grid_cost_eur")},
                     "efficiency_fit": fit, "warnings": ["Generic prepared interval window; not historical reference acceptance"],
                     "message": "Vorläufige SIM mit aufbereiteten Messwerten; historische Abnahme separat"}
            audit["reference_totals"]["fixed_grid_cost_eur"] = (
                audit["reference_totals"]["grid_import_wh"] / 1000 * .32)
            data = {"schema_version": 1, "energy_basis": "ac_equivalent_wh",
                    "data_kind": checked["data_kind"], "source_sha256": [checked["source_sha256"]],
                    "load_scope": "whole_site_including_loadpoints", "tariff_basis": "retail_final_eur_kwh",
                    "e3dc": battery, "pv_source": context.get("pv_source"), "rows": inputs,
                    "measured_intervals": observed, "historical_audit": audit}
        data["measurement_preparation"] = {"audit": copy.deepcopy(checked["audit"]),
                                           "mapping_sha256": checked["mapping_sha256"],
                                           "source_sha256": checked["source_sha256"],
                                           "interval_mean_power_derived": interval_means,
                                           "provisional_measurement_reasons": provisional_reasons,
                                           "provisional_power_integration": provisional}
        data["source_sha256"] = [checked["source_sha256"], checked["mapping_sha256"], digest(context)]
        if provisional:
            audit = data["historical_audit"]
            audit["status"], audit["historical_acceptance_passed"] = "warnings", False
            audit["warnings"].append("Power integrated by bounded left hold; derived, provisional measurement")
            audit["message"] += " · VORLÄUFIG: Leistungsintegration"
        if interval_means:
            data["historical_audit"]["interval_energy_provenance"] = (
                "Original interval-mean power integrated over its documented duration; not left hold or direct interval metering")
        if provisional_reasons:
            audit = data["historical_audit"]
            audit["status"], audit["historical_acceptance_passed"] = "warnings", False
            audit["warnings"].extend(provisional_reasons)
            audit["message"] = "VORLÄUFIG · Messenergien vollständig · SoC-/Bilanzabnahme offen"
        validate(data)
        return data
    except EnergyDataError as exc:
        raise SimulationError(str(exc)) from None

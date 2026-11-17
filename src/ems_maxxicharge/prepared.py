"""Admission of shared prepared measurements; simulator physics stays unchanged."""

import copy
import csv
import io
import math

from eos_pv_helper.energy_data import EnergyDataError, verify_prepared

from .config import BatteryConfig, SimulationError, construct
from .history import ENERGY, fit_efficiencies, import_csv
from .inputs import digest, validate


def from_prepared(source, context):
    try:
        checked = verify_prepared(source)
        rows = checked["rows"]
        if checked["audit"]["status"] != "passed":
            raise SimulationError("Incomplete/imbalanced measurements cannot enter the simulator")
        battery = construct(BatteryConfig, context.get("e3dc"))
        battery = {**battery.__dict__, "initial_soc_percent": rows[0]["soc_start_percent"]}
        inputs = [{k: r[k] for k in ("start_utc", "end_utc", "load_wh", "base_pv_wh",
                                    "import_eur_kwh", "export_eur_kwh")} for r in rows]
        observed = [{**r, "battery_charge_ac_wh": r["battery_charge_wh"],
                     "battery_discharge_ac_wh": r["battery_discharge_wh"]} for r in rows]
        provisional = any("power" in q["status"] for r in rows for q in r["quality"].values())
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
            fit = fit_efficiencies(observed, battery["capacity_wh"])
            # Generic future/backtest windows are not November regression admission.
            audit = {"status": "warnings", "historical_acceptance_passed": False,
                     "original_hours": len(rows), "source_kind": checked["data_kind"],
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
                                           "provisional_power_integration": provisional}
        data["source_sha256"] = [checked["source_sha256"], checked["mapping_sha256"], digest(context)]
        if provisional:
            audit = data["historical_audit"]
            audit["status"], audit["historical_acceptance_passed"] = "warnings", False
            audit["warnings"].append("Power integrated by bounded left hold; derived, provisional measurement")
            audit["message"] += " · VORLÄUFIG: Leistungsintegration"
        validate(data)
        return data
    except EnergyDataError as exc:
        raise SimulationError(str(exc)) from None

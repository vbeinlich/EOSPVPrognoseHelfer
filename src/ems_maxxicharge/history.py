"""Audit original HA hourly interval exports; no API, SQL, resampling or backfill."""

import csv
import hashlib
import io
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import BatteryConfig, SimulationError, construct, number
from .inputs import canonical, stamp, validate

REFERENCE = {"load_wh": 227880, "base_pv_wh": 64100, "grid_import_wh": 168230,
             "grid_cost_eur": 67.17, "fixed_grid_cost_eur": 53.83}
ENERGY = ("load_wh", "base_pv_wh", "grid_import_wh", "grid_export_wh",
          "battery_charge_wh", "battery_discharge_wh")
START = datetime(2026, 11, 9, 23, tzinfo=UTC)  # 10 Nov 00:00 Europe/Berlin
END = datetime(2026, 11, 14, 23, tzinfo=UTC)  # 15 Nov 00:00 Europe/Berlin


def export_timestamp(value, context):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            if context.get("naive_local_time_acknowledged") is not True:
                raise SimulationError("Naive CSV timestamp needs explicit local-time acknowledgement")
            zone = ZoneInfo(context["timezone"])
            first, second = parsed.replace(tzinfo=zone, fold=0), parsed.replace(tzinfo=zone, fold=1)
            if first.utcoffset() != second.utcoffset():
                raise SimulationError("Ambiguous or nonexistent local timestamp")
            parsed = first
        return parsed.astimezone(UTC)
    except (ValueError, AttributeError, KeyError):
        raise SimulationError("Invalid CSV timestamp") from None


def parse_number(value, context):
    if not isinstance(value, str) or not value.strip():
        raise SimulationError("Missing measured CSV value; no zero fill")
    text = value.strip()
    decimal = context.get("decimal_separator", ".")
    if decimal not in (".", ","):
        raise SimulationError("Invalid CSV decimal convention")
    if decimal == ",":
        if "." in text:
            raise SimulationError("Thousands separators or ambiguous CSV number")
        text = text.replace(",", ".")
    try:
        return number(float(text), "CSV value")
    except ValueError:
        raise SimulationError("Invalid numeric CSV value") from None


def fit_efficiencies(rows, capacity):
    xx = xy = yy = xb = yb = 0.0
    for r in rows:
        c, d = r["battery_charge_ac_wh"], r["battery_discharge_ac_wh"]
        change = capacity * (r["soc_end_percent"] - r["soc_start_percent"]) / 100
        xx += c * c
        xy += c * d
        yy += d * d
        xb += c * change
        yb += d * change
    determinant = xx * yy - xy * xy
    if determinant <= max(1, xx * yy) * 1e-10:
        return {"status": "not_identifiable", "applied_to_simulation": False}
    charging = (xb * yy - yb * xy) / determinant
    discharge_coefficient = (yb * xx - xb * xy) / determinant
    discharging = -1 / discharge_coefficient if discharge_coefficient < 0 else None
    return {"status": "plausible" if 0 < charging <= 1 and discharging is not None and 0 < discharging <= 1
            else "implausible_basis_or_timestamps", "charging_efficiency_ac_to_internal": charging,
            "discharging_efficiency_internal_to_ac": discharging, "applied_to_simulation": False}


def import_csv(raw, context):
    if not isinstance(raw, bytes) or len(raw) > 16_000_000:
        raise SimulationError("Historical CSV missing or oversized")
    if (context.get("energy_kind") != "measured_interval_integrals"
            or context.get("load_scope") != "whole_site_including_loadpoints"
            or context.get("tariff_basis") != "retail_final_eur_kwh"
            or context.get("battery_basis") not in ("ac_bus", "dc_bus")
            or context.get("tariff_aggregation") not in (
                "constant_within_hour", "energy_weighted_hour", "hourly_mean_approximation_acknowledged")):
        raise SimulationError("Historical units, meter boundary, load scope or LUOX tariff aggregation unconfirmed")
    mapping, units = context.get("columns", {}), context.get("units", {})
    battery = construct(BatteryConfig, context.get("e3dc"))
    if battery.capacity_wh != 13000:
        raise SimulationError("Historical reference requires explicitly confirmed 13 kWh E3/DC capacity")
    try:
        table = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter=context.get("delimiter", ","))
        if not table.fieldnames or len(set(table.fieldnames)) != len(table.fieldnames):
            raise SimulationError("Invalid or duplicate CSV column headers")
        originals = list(table)
    except (UnicodeError, csv.Error, TypeError):
        raise SimulationError("Invalid CSV encoding or delimiter") from None
    if len(originals) > 10000:
        raise SimulationError("Historical export exceeds bounded import")
    rows, observed, excluded = [], [], 0
    for source in originals:
        def cell(key):
            name = mapping.get(key, key)
            if name not in source or source[name] is None:
                raise SimulationError("Required original CSV column missing: " + key)
            return source[name]
        at = export_timestamp(cell("start_utc"), context)
        if not START <= at < END:
            excluded += 1
            continue
        end = export_timestamp(cell("end_utc"), context)
        if end - at != timedelta(hours=1):
            raise SimulationError("Historical reference must use original complete hourly intervals")
        values = {}
        for key in ENERGY:
            unit = units.get(key)
            if unit not in ("Wh", "kWh"):
                raise SimulationError("Explicit interval energy unit required")
            values[key] = number(parse_number(cell(key), context), key, 0) * (1000 if unit == "kWh" else 1)
        price = parse_number(cell("import_eur_kwh"), context)
        feed = parse_number(cell("export_eur_kwh"), context)
        soc_start = number(parse_number(cell("soc_start_percent"), context), "SOC", 0, 100)
        soc_end = number(parse_number(cell("soc_end_percent"), context), "SOC", 0, 100)
        start_point = export_timestamp(cell("soc_start_at_utc"), context)
        end_point = export_timestamp(cell("soc_end_at_utc"), context)
        if not (0 <= (at - start_point).total_seconds() <= 60
                and 0 <= (end - end_point).total_seconds() <= 60):
            raise SimulationError("SOC timestamps do not establish boundary SOC without future values")
        c, d = values["battery_charge_wh"], values["battery_discharge_wh"]
        if context["battery_basis"] == "dc_bus":
            c /= number(context.get("inverter_ac_to_dc_efficiency"), "inverter charge efficiency", .01, 1)
            d *= number(context.get("inverter_dc_to_ac_efficiency"), "inverter discharge efficiency", .01, 1)
        site_error = values["base_pv_wh"] + values["grid_import_wh"] + d - values["load_wh"] - values["grid_export_wh"] - c
        soc_error = battery.capacity_wh * (soc_end - soc_start) / 100 - (
            c * battery.charge_efficiency - d / battery.discharge_efficiency)
        observed.append({**values, "start_utc": at.isoformat(), "end_utc": end.isoformat(),
            "battery_charge_ac_wh": c, "battery_discharge_ac_wh": d,
            "soc_start_percent": soc_start, "soc_end_percent": soc_end,
            "soc_start_at_utc": start_point.isoformat(), "soc_end_at_utc": end_point.isoformat(),
            "site_balance_error_wh": site_error, "soc_model_error_wh": soc_error,
            "grid_cost_eur": values["grid_import_wh"] / 1000 * price,
            "fixed_grid_cost_eur": values["grid_import_wh"] / 1000 * .32,
            "feed_in_revenue_eur": values["grid_export_wh"] / 1000 * feed})
        rows.append({"start_utc": at.isoformat(), "end_utc": end.isoformat(),
                     "load_wh": values["load_wh"], "base_pv_wh": values["base_pv_wh"],
                     "import_eur_kwh": price, "export_eur_kwh": feed})
    if len(rows) != 120 or stamp(rows[0]["start_utc"]) != START or stamp(rows[-1]["end_utc"]) != END:
        raise SimulationError("The 10–14 November reference requires exactly 120 original hours")
    if any(stamp(b["start_utc"]) != stamp(a["end_utc"]) for a, b in zip(rows, rows[1:])):
        raise SimulationError("Historical CSV is unordered, duplicated or has recording gaps")
    if any(abs(a["soc_end_percent"] - b["soc_start_percent"]) > .01 for a, b in zip(observed, observed[1:])):
        raise SimulationError("SOC boundaries are inconsistent between adjacent original hours")
    site_tolerance = number(context.get("site_balance_tolerance_wh", 50), "site tolerance", 0, 500)
    soc_tolerance = number(context.get("soc_model_tolerance_wh", 200), "SOC tolerance", 0, 500)
    max_site = max(abs(r["site_balance_error_wh"]) for r in observed)
    if max_site > site_tolerance:
        raise SimulationError("Measured site energy boundary is inconsistent; no calibrated comparison")
    summary = {k: math.fsum(r[k] for r in observed) for k in (
        "load_wh", "base_pv_wh", "grid_import_wh", "grid_export_wh", "grid_cost_eur",
        "fixed_grid_cost_eur", "feed_in_revenue_eur", "battery_charge_ac_wh", "battery_discharge_ac_wh")}
    summary["net_electricity_cost_eur"] = summary["grid_cost_eur"] - summary["feed_in_revenue_eur"]
    deltas = {k: summary[k] - expected for k, expected in REFERENCE.items()}
    kind = context.get("data_kind", "measured")
    if kind not in ("measured", "synthetic"):
        raise SimulationError("Historical CSV data kind invalid")
    if kind == "measured" and any(abs(v) > (.15 if k.endswith("eur") else 50) for k, v in deltas.items()):
        raise SimulationError("Original hourly export differs from reported November reference totals")
    warnings = []
    efficiency_fit = fit_efficiencies(observed, battery.capacity_wh)
    if kind == "measured" and efficiency_fit["status"] != "plausible":
        warnings.append("Battery efficiencies not identifiable or physically plausible from original intervals")
    if max(abs(r["soc_model_error_wh"]) for r in observed) > soc_tolerance:
        warnings.append("Battery efficiency or SOC timing model not calibrated")
    if context["tariff_aggregation"] == "hourly_mean_approximation_acknowledged":
        warnings.append("Hourly tariff approximation: intrahour LUOX price/energy alignment unproven")
    audit = {"status": "warnings" if warnings else "passed", "original_hours": 120,
             "historical_acceptance_passed": not warnings and kind == "measured",
             "excluded_rows": excluded, "excluded_dates": ["2026-11-08", "2026-11-09"],
             "source_kind": kind, "reference_totals": summary, "reported_reference_deltas": deltas,
             "max_site_balance_error_wh": max_site,
             "max_soc_model_error_wh": max(abs(r["soc_model_error_wh"]) for r in observed),
             "efficiency_fit": efficiency_fit, "warnings": warnings,
             "message": "120 originale HA-Stunden geprüft · 10.–14.11.2026 · "
             + ("SYNTHETISCHE TESTDATEN" if kind == "synthetic" else "Messreferenz")
             + (" · Kalibrierungshinweise beachten" if warnings else "")}
    e3 = {**battery.__dict__, "initial_soc_percent": observed[0]["soc_start_percent"]}
    data = {"schema_version": 1, "energy_basis": "ac_equivalent_wh", "data_kind": kind,
            "source_sha256": [hashlib.sha256(raw).hexdigest(), hashlib.sha256(canonical(context)).hexdigest()],
            "load_scope": "whole_site_including_loadpoints", "tariff_basis": "retail_final_eur_kwh",
            "e3dc": e3, "pv_source": context.get("pv_source"), "rows": rows,
            "historical_audit": audit, "measured_intervals": observed}
    validate(data)
    return data

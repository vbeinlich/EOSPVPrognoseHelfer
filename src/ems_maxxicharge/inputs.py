"""Strict local input contracts; never fetch, integrate W samples or fill gaps."""

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import BatteryConfig, SimulationError, construct, number

MAX_BYTES = 64_000_000
MAX_ROWS = 35136  # A leap year of quarter hours; bounded offline workload.


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def stamp(value):
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if at.utcoffset() is None:
            raise ValueError()
        return at.astimezone(UTC)
    except (TypeError, ValueError, AttributeError):
        raise SimulationError("Timestamp requires an explicit UTC offset") from None


def read_json(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise SimulationError("Input is a symlink or exceeds the size limit")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise SimulationError("Input exceeds the size limit")
    try:
        def pairs(items):
            obj = {}
            for key, value in items:
                if key in obj:
                    raise SimulationError("Duplicate JSON key")
                obj[key] = value
            return obj
        return json.loads(raw, object_pairs_hook=pairs), hashlib.sha256(raw).hexdigest()
    except (ValueError, UnicodeError):
        raise SimulationError("Invalid JSON input") from None


def validate(data):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
        raise SimulationError("Invalid simulation input contract")
    if (data["schema_version"] != 1 or data.get("energy_basis") != "ac_equivalent_wh"
            or data.get("data_kind") not in ("synthetic", "archived_forecast", "measured")
            or data.get("load_scope") != "whole_site_including_loadpoints"
            or data.get("tariff_basis") != "retail_final_eur_kwh"):
        raise SimulationError("Input units, provenance, load scope or tariff basis missing")
    hashes = data.get("source_sha256")
    if not isinstance(hashes, list) or not hashes or any(
            not isinstance(h, str) or not re.fullmatch("[a-f0-9]{64}", h) for h in hashes):
        raise SimulationError("Original source hashes are required")
    battery = construct(BatteryConfig, data.get("e3dc"))
    raw_rows = data.get("rows")
    if not isinstance(raw_rows, list) or not 1 <= len(raw_rows) <= MAX_ROWS:
        raise SimulationError("No complete bounded interval series")
    rows, previous = [], None
    for raw in raw_rows:
        if not isinstance(raw, dict):
            raise SimulationError("Interval must be an object")
        at, end = stamp(raw.get("start_utc")), stamp(raw.get("end_utc"))
        seconds = (end - at).total_seconds()
        if seconds not in (900, 3600) or previous is not None and at != previous:
            raise SimulationError("Gap, duplicate, overlap or unsupported interval duration")
        if data["data_kind"] == "measured" and end > datetime.now(UTC):
            raise SimulationError("Future intervals are not measurements")
        row = {"at": at, "start_utc": at.isoformat(), "end_utc": end.isoformat(),
               "interval_seconds": int(seconds)}
        for key in ("load_wh", "base_pv_wh", "import_eur_kwh", "export_eur_kwh"):
            row[key] = number(raw.get(key), key, 0 if key.endswith("_wh") else None)
        for key in ("weather", "planes"):
            if key in raw:
                if not isinstance(raw[key], dict):
                    raise SimulationError("Invalid PV source interval")
                row[key] = raw[key]
        rows.append(row)
        previous = end
    if not isinstance(data.get("pv_source"), dict):
        raise SimulationError("PV source metadata missing")
    return rows, battery


def from_eos(solution, source_sha, *, context):
    """Reuse original run inputs; never pretend solver forecasts are measurements.

    Scope, PV basis, inverter boundary and reference geometry require an explicit
    offline context. Historical controls are not changed or executed.
    """
    if (solution.get("controls_start_at_now") is not True
            or solution.get("interval_seconds") not in (900, 3600)
            or context.get("load_scope_model_assumption_acknowledged") is not True
            or context.get("pv_conversion_assumption_acknowledged") is not True
            or context.get("constant_efficiency_model_acknowledged") is not True):
        raise SimulationError("EOS run time basis or explicit modelling context is missing")
    params = solution.get("parameters", {})
    ems, bat, inv = [params.get(k, {}) for k in ("ems", "pv_battery", "inverter")]
    if params.get("forecast_interval_seconds") != solution["interval_seconds"]:
        raise SimulationError("EOS input and run interval duration mismatch")
    seconds = solution["interval_seconds"]
    pv_factor = number(context.get("pv_conversion_factor_to_ac_equivalent"),
                       "declared PV conversion factor", 0.01, 1)
    count = len(solution.get("ac_charge", []))
    if not 1 <= count <= MAX_ROWS:
        raise SimulationError("EOS control horizon is missing")
    keys = ("pv_forecast_wh", "total_load", "electricity_price_per_wh", "feed_in_tariff_per_wh")
    arrays = [ems.get(k) for k in keys]
    if any(not isinstance(a, list) or len(a) < count for a in arrays):
        raise SimulationError("Original EOS PV/load/tariff inputs are incomplete")
    # Do not silently flatten a load-dependent inverter curve.
    if inv.get("dc_to_ac_efficiency_curve") is not None:
        raise SimulationError("Load-dependent EOS inverter needs a separately validated adapter")
    capacity = number(bat.get("capacity_wh"), "EOS battery capacity", 1)
    charge_eff = number(bat.get("charging_efficiency"), "EOS charging efficiency", 0.01, 1)
    discharge_eff = number(bat.get("discharging_efficiency"), "EOS discharging efficiency", 0.01, 1)
    ac_dc = number(inv.get("ac_to_dc_efficiency"), "EOS AC/DC efficiency", 0.01, 1)
    dc_ac = number(inv.get("dc_to_ac_efficiency"), "EOS DC/AC efficiency", 0.01, 1)
    e3dc = {
        "capacity_wh": capacity,
        "min_soc_percent": bat.get("min_soc_percentage"),
        "initial_soc_percent": bat.get("initial_soc_percentage"),
        "max_soc_percent": bat.get("max_soc_percentage"),
        "max_discharge_w": number(inv.get("max_power_wh"), "EOS inverter power", 0),
        "max_pv_charge_w": number(bat.get("max_charge_power_w"), "EOS charge power", 0),
        "max_grid_charge_w": 0,  # E3/DC self-consumption reference, not a replay of its controller.
        "charge_efficiency": charge_eff * ac_dc,
        "discharge_efficiency": discharge_eff * dc_ac,
        "wear_eur_per_kwh_output": context.get("e3dc_wear_eur_per_kwh_output", 0),
    }
    start = stamp(solution.get("start_solution_datetime"))
    rows = []
    for i in range(count):
        rows.append({"start_utc": (start + timedelta(seconds=i * seconds)).isoformat(),
                     "end_utc": (start + timedelta(seconds=(i + 1) * seconds)).isoformat(),
                     "base_pv_wh": number(arrays[0][i], "EOS PV", 0) * pv_factor,
                     "load_wh": arrays[1][i],
                     "import_eur_kwh": number(arrays[2][i], "EOS import price") * 1000,
                     "export_eur_kwh": number(arrays[3][i], "EOS export price") * 1000})
    return {"schema_version": 1, "data_kind": "archived_forecast",
            "energy_basis": "ac_equivalent_wh", "source_sha256": [source_sha],
            "load_scope": "whole_site_including_loadpoints",
            "tariff_basis": "retail_final_eur_kwh", "rows": rows, "e3dc": e3dc,
            "pv_source": context["pv_source"],
            "e3dc_model": "constant combined battery/inverter efficiencies; self-consumption",
            "scope_evidence": "whole-site load modelling assumption, meter scope unconfirmed",
            "pv_conversion_factor_to_ac_equivalent": pv_factor,
            "model_context_sha256": digest(context)}


def from_actuals(data, source_sha, *, context):
    """Adapter for the existing PLAN_ACTUAL.md measured interval contract.

    Validates through the existing reader; no recorder SQL or network access.
    A row cannot span multiple retail tariffs: no invented intrainterval split.
    """
    from eos_pv_helper.plan_actual import Actuals, ActualsError

    try:
        actual = Actuals(canonical(data))
        if not (actual.house_scope and actual.pv_ac and actual.retail):
            raise SimulationError("Measured scope, AC PV or final retail tariff is unconfirmed")
        rows = []
        for start, end, values in actual.energy:
            tariffs = [v for a, b, v in actual.tariffs if a <= start and b >= end]
            if len(tariffs) != 1:
                raise SimulationError("Exact measured interval tariff coverage is missing")
            row = {"start_utc": start.isoformat(), "end_utc": end.isoformat(),
                   "load_wh": values.get("load_wh"), "base_pv_wh": values.get("pv_wh"),
                   "import_eur_kwh": tariffs[0].get("retail_eur_kwh"),
                   "export_eur_kwh": context.get("export_eur_kwh")}
            rows.append(row)
        # Extra weather/planes can be joined only by exact interval identity.
        extras = context.get("pv_intervals", [])
        if extras:
            if len(extras) != len(rows):
                raise SimulationError("PV context interval coverage mismatch")
            for row, extra in zip(rows, extras):
                if (stamp(extra.get("start_utc")) != stamp(row["start_utc"])
                        or stamp(extra.get("end_utc")) != stamp(row["end_utc"])):
                    raise SimulationError("PV context timestamps mismatch")
                for key in ("planes", "weather"):
                    if key in extra:
                        row[key] = extra[key]
        result = {"schema_version": 1, "data_kind": "measured",
                  "energy_basis": "ac_equivalent_wh", "source_sha256": [source_sha],
                  "load_scope": "whole_site_including_loadpoints",
                  "tariff_basis": "retail_final_eur_kwh", "rows": rows,
                  "e3dc": context.get("e3dc"), "pv_source": context.get("pv_source")}
        validate(result)
        return result
    except ActualsError:
        raise SimulationError("Existing measured input contract validation failed") from None

"""Shared, offline measurement preparation for history and incremental arrivals.

No network, recorder access, device control, gap filling or counter allocation.
Intervals are half-open in UTC. Every derived value retains its source records.
"""

import bisect
import copy
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .plan_actual import ActualsError, number

EnergyDataError = ActualsError
ENERGY = ("load_wh", "base_pv_wh", "grid_import_wh", "grid_export_wh",
          "battery_charge_wh", "battery_discharge_wh")
REQUIRED = (*ENERGY, "grid_cost_eur", "import_eur_kwh", "export_eur_kwh")
PRIORITY = {"interval": 0, "counter": 1, "mean_power": 2, "power": 3, "state": 0}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def timestamp(value, config):
    """Explicit offsets preferred; ambiguous/nonexistent Berlin wall times fail."""
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if at.utcoffset() is None:
            if config.get("naive_local_time_acknowledged") is not True:
                raise ValueError()
            zone = ZoneInfo(config.get("timezone", "Europe/Berlin"))
            a, b = at.replace(tzinfo=zone, fold=0), at.replace(tzinfo=zone, fold=1)
            if a.utcoffset() != b.utcoffset():
                raise ValueError()
            at = a
        return at.astimezone(UTC)
    except (ValueError, TypeError, AttributeError, KeyError):
        raise EnergyDataError("Timestamp needs an unambiguous original timezone") from None


def ac_energy(value, metric, basis, config):
    if basis == "ac_bus":
        return value
    if basis != "dc_bus":
        raise EnergyDataError("Explicit AC/DC meter boundary required")
    if metric == "battery_charge_wh":
        return value / efficiency(config, "inverter_ac_to_dc_efficiency")
    if metric in ("battery_discharge_wh", "base_pv_wh"):
        return value * efficiency(config, "inverter_dc_to_ac_efficiency")
    raise EnergyDataError("Unsupported DC boundary for this quantity")


def efficiency(config, key):
    value = number(config.get(key))
    if not 0 < value <= 1:
        raise EnergyDataError("Explicit inverter efficiency in (0,1] required")
    return value


def site_balance(values):
    """One AC-bus balance used by every adapter, including the legacy CSV audit."""
    if any(values.get(k) is None for k in ENERGY if k != "load_wh"):
        return None, None
    site = math.fsum((values["base_pv_wh"], values["grid_import_wh"],
                      values["battery_discharge_wh"], -values["grid_export_wh"],
                      -values["battery_charge_wh"]))
    return site, site - values["load_wh"] if values.get("load_wh") is not None else None


def validate_mapping(config):
    if config.get("schema_version") != 1 or not isinstance(config.get("metrics"), dict):
        raise EnergyDataError("Invalid energy mapping schema")
    if config.get("data_kind", "measured") not in ("measured", "synthetic"):
        raise EnergyDataError("Measured or explicitly synthetic source required")
    if (config.get("tariff_basis") != "retail_final_eur_kwh"
            or config.get("grid_cost_scope") != "energy_import_only"):
        raise EnergyDataError("Final retail tariff and energy-only cost boundary must be explicit")
    groups = config.get("load_components")
    metrics = config["metrics"]
    if (not isinstance(groups, list) or not groups or len(set(groups)) != len(groups)
            or "load_wh" in metrics):
        raise EnergyDataError("Site consumption requires distinct configured components")
    covers, entities = set(), {}
    for name, spec in metrics.items():
        sources = spec.get("sources", [])
        if not isinstance(sources, list) or not sources:
            raise EnergyDataError("Each metric requires explicit sources")
        if name in groups:
            scope = spec.get("covers", [])
            if (not scope or len(set(scope)) != len(scope) or covers.intersection(scope)):
                raise EnergyDataError("Overlapping or unknown consumer groups")
            covers.update(scope)
        for source in sources:
            entity, kind = source.get("entity_id"), source.get("kind")
            if (not isinstance(entity, str) or not entity or kind not in PRIORITY
                    or entity in config.get("excluded_entities", [])):
                raise EnergyDataError("Invalid or explicitly excluded sensor mapping")
            if entity in entities and entities[entity] != name:
                raise EnergyDataError("One sensor cannot count toward two quantities")
            entities[entity] = name
            unit = source.get("unit")
            allowed = (("W", "kW") if kind in ("power", "mean_power") else
                       ("%", "EUR/kWh") if kind == "state" else
                       ("EUR/kWh",) if name in ("import_eur_kwh", "export_eur_kwh") else
                       ("EUR", "€") if name == "grid_cost_eur" else ("Wh", "kWh"))
            if unit not in allowed or kind in ("power", "mean_power") and not name.endswith("_wh"):
                raise EnergyDataError("Unit does not match sensor semantics")
            if source.get("derivation", "direct") not in (
                    "direct", "derived_counter", "derived_power_left_hold", "derived_interval_mean_power"):
                raise EnergyDataError("Unknown original interval derivation")
            if kind == "mean_power" or source.get("derivation") == "derived_interval_mean_power":
                duration = source.get("mean_interval_seconds")
                if type(duration) is not int or not 0 < duration <= 3600:
                    raise EnergyDataError("Original mean-power interval duration required")
            if kind == "state" and (name, unit) not in (
                    ("soc_percent", "%"), ("import_eur_kwh", "EUR/kWh"),
                    ("export_eur_kwh", "EUR/kWh")):
                raise EnergyDataError("Invalid state sensor semantics")
            if name.endswith("_wh"):
                ac_energy(1, name, source.get("basis"), config)
            if kind == "power":
                if source.get("integration") != "left_hold":
                    raise EnergyDataError("Power integration method must be explicit")
                if not 0 < number(source.get("max_gap_seconds")) <= 3600:
                    raise EnergyDataError("Bounded original power coverage required")
    if any(g not in metrics for g in groups):
        raise EnergyDataError("Unknown load component")
    tolerance = number(config.get("site_balance_tolerance_wh", 50))
    if not 0 <= tolerance <= 500:
        raise EnergyDataError("Site tolerance must remain within historical limits")


def observations_from_ha(history):
    """Flatten an existing HA history GET export, preserving each original object.

    last_updated is an observation time, never an invented energy boundary.
    Unknown states remain explicit missing observations, interrupting integration.
    """
    result = []
    for series in history:
        if not isinstance(series, list):
            raise EnergyDataError("Expected HA history series")
        for record in series:
            result.append({"entity_id": record.get("entity_id"),
                           "at": record.get("last_updated"), "value": record.get("state"),
                           "unit": record.get("attributes", {}).get("unit_of_measurement"),
                           "original": copy.deepcopy(record)})
    return result


class MeasurementBuffer:
    """Append-only inputs; new/late arrivals recompute through the same prepare().

    Persist the original observations externally if used by a collector. No daemon
    is installed here. as_of is the event-time/arrival watermark supplied by caller.
    """

    def __init__(self, config):
        validate_mapping(config)
        self.config = copy.deepcopy(config)
        self.observations = []

    def extend(self, records):
        if not isinstance(records, list) or len(records) + len(self.observations) > 500000:
            raise EnergyDataError("Invalid or oversized observation collection")
        self.observations.extend(copy.deepcopy(records))

    def prepare(self, start, end, *, as_of):
        return prepare(self.observations, self.config, start, end, as_of=as_of)


def _series(records, source, config, as_of):
    result = {}
    for index, raw in records:
        key = "start" if source["kind"] in ("interval", "mean_power") else "at"
        if key not in raw and ("at" if key == "start" else "start") in raw:
            continue
        at = timestamp(raw.get(key), config)
        received = timestamp(raw.get("received_at", raw.get(key)), config)
        finish = timestamp(raw.get("end"), config) if key == "start" else at
        if finish > as_of or at > as_of or received > as_of:
            continue
        if raw.get("unit") != source["unit"]:
            raise EnergyDataError("Original unit missing or differs from mapping")
        value = raw.get("value")
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                value = None
        if value is not None:
            value = number(value, nonnegative=source["unit"] not in ("EUR/kWh", "EUR", "€"))
            if source["unit"] == "%" and not 0 <= value <= 100:
                raise EnergyDataError("SOC outside physical range")
        if source["kind"] == "mean_power":
            if (finish - at).total_seconds() != source["mean_interval_seconds"]:
                raise EnergyDataError("Original mean-power interval duration differs from mapping")
        elif source.get("derivation") == "derived_interval_mean_power":
            # Imported aggregated Wh: retain upstream mean-power provenance and
            # source-declared coverage; never reinterpret as instantaneous samples.
            expected = (finish - at).total_seconds() / source["mean_interval_seconds"]
            coverage = raw.get("mean_power_coverage", "")
            if not expected.is_integer() or coverage != f"{int(expected)}/{int(expected)}":
                value = None
        if type(raw.get("reset", False)) is not bool:
            raise EnergyDataError("Counter reset indication must be boolean")
        record = (at, finish, value, index, received, raw.get("reset", False),
                  hashlib.sha256(canonical(raw)).hexdigest())
        identity = (at, finish)
        previous = result.get(identity)
        if previous and (previous[2], previous[5]) != (value, record[5]):
            # A revision is admissible only with explicit, distinct arrival times.
            if previous[4] == received:
                raise EnergyDataError("Conflicting observations need explicit revision times")
            if previous[4] > received:
                continue
        elif previous and (previous[4] > received or
                           previous[4] == received and previous[6] <= record[6]):
            continue
        result[identity] = record
    rows = sorted(result.values())
    if source["kind"] in ("interval", "mean_power") and any(b[0] < a[1] for a, b in zip(rows, rows[1:])):
        raise EnergyDataError("Original energy intervals overlap")
    return rows


def _extract(series, source, left, right, *, point=False):
    """Return value, derivation, record indices, issue; never prorate energy."""
    kind = source["kind"]
    times = [r[0] for r in series]
    if point:
        i = bisect.bisect_right(times, left) - 1
        max_age = source.get("max_age_seconds", 60)
        if not 0 <= number(max_age) <= 60:
            raise EnergyDataError("SOC observation age cannot exceed historical limit")
        if i < 0 or series[i][2] is None:
            return None, "incomplete", [], "missing_boundary_soc"
        if (left - series[i][0]).total_seconds() > max_age:
            return None, "incomplete", [series[i][3]], "stale_boundary_soc"
        return series[i][2], "direct", [series[i][3]], None
    if kind == "counter":
        a, b = bisect.bisect_left(times, left), bisect.bisect_left(times, right)
        if a >= len(series) or b >= len(series) or times[a] != left or times[b] != right:
            return None, "incomplete", [], "missing_exact_counter_boundary"
        window = series[a:b + 1]
        ids = [r[3] for r in window]
        if any(r[2] is None for r in window):
            return None, "incomplete", ids, "unavailable_counter"
        if any(r[5] for r in window[1:]):
            return None, "incomplete", ids, "explicit_counter_reset"
        if source["unit"] not in ("EUR", "€") and any(y[2] < x[2] for x, y in zip(window, window[1:])):
            return None, "incomplete", ids, "counter_reset"
        return window[-1][2] - window[0][2], "derived_counter", ids, None
    if kind in ("interval", "mean_power"):
        selected = [r for r in series if r[0] < right and r[1] > left]
        ids = [r[3] for r in selected]
        if (not selected or selected[0][0] != left or selected[-1][1] != right
                or any(a[1] != b[0] for a, b in zip(selected, selected[1:]))
                or any(r[1] <= r[0] or r[2] is None for r in selected)):
            return None, "incomplete", ids, "missing_original_interval_coverage"
        if source["unit"] == "EUR/kWh":
            if len({r[2] for r in selected}) != 1:
                return None, "incomplete", ids, "changing_tariff_without_aligned_energy"
            return selected[0][2], "direct", ids, None
        if kind == "mean_power":
            return math.fsum(r[2] * (r[1] - r[0]).total_seconds() / 3600 for r in selected), "derived_interval_mean_power", ids, None
        return math.fsum(r[2] for r in selected), "direct", ids, None
    if kind == "state":
        # Tariffs must explicitly cover the full interval; state carry is forbidden.
        return None, "incomplete", [], "tariff_needs_explicit_interval"
    i = max(0, bisect.bisect_right(times, left) - 1)
    cursor, parts, ids = left, [], []
    for a, b in zip(series[i:], series[i + 1:]):
        if a[0] >= right:
            break
        begin, finish = max(left, a[0]), min(right, b[0])
        if finish <= begin:
            continue
        if (begin != cursor or a[2] is None
                or (b[0] - a[0]).total_seconds() > source["max_gap_seconds"]):
            return None, "incomplete", ids, "uncovered_power_or_stale_sample"
        parts.append(a[2] * (finish - begin).total_seconds() / 3600)
        ids.extend((a[3], b[3]))
        cursor = finish
    if cursor != right:
        return None, "incomplete", ids, "missing_power_end_coverage"
    return math.fsum(parts), "derived_power_left_hold", sorted(set(ids)), None


def _metric(metric, spec, series, config, left, right, *, point=False):
    failures = []
    # Stable ordering preserves configured preference between equivalent sources.
    for source in sorted(spec["sources"], key=lambda s: max(PRIORITY[s["kind"]],
                         {"direct": 0, "derived_counter": 1, "derived_interval_mean_power": 2,
                          "derived_power_left_hold": 3}.get(s.get("derivation"), 0))):
        value, quality, ids, issue = _extract(series[id(source)], source, left, right, point=point)
        if issue:
            detail = {"entity_id": source["entity_id"], "issue": issue, "records": ids}
            if point and ids:
                original = next(r for r in series[id(source)] if r[3] == ids[0])
                detail.update(observed_at_utc=original[0].isoformat(), observed_percent=original[2],
                              age_seconds=(left - original[0]).total_seconds())
            failures.append(detail)
            continue
        original = value
        if source["kind"] == "interval":
            quality = source.get("derivation", quality)
        if source["unit"] in ("kWh", "kW"):
            value *= 1000
        if metric.endswith("_wh"):
            value = ac_energy(value, metric, source.get("basis"), config)
            if source.get("basis") == "dc_bus":
                quality += "+dc_to_ac"
        detail = {"status": quality, "entity_id": source["entity_id"], "records": ids,
                  "original_value": original, "original_unit": source["unit"],
                  "basis": source.get("basis"), "rejected_candidates": failures}
        if source["kind"] == "mean_power":
            detail.pop("original_value")  # Integrated Wh is not an original W sample.
            detail["interval_mean_integration"] = {"energy_wh": value,
                "source_interval_seconds": source["mean_interval_seconds"], "method": "mean_times_original_duration"}
        return value, detail
    return None, {"status": "incomplete", "rejected_candidates": failures}


def prepare(observations, config, start, end, *, as_of):
    """Same deterministic path for old exports and a growing observation buffer."""
    validate_mapping(config)
    if not isinstance(observations, list) or len(observations) > 500000:
        raise EnergyDataError("Invalid or oversized original measurements")
    left, stop, now = [timestamp(t, config) for t in (start, end, as_of)]
    if config.get("data_kind", "measured") == "measured":
        now = min(now, datetime.now(UTC))
    seconds = config.get("interval_seconds", 3600)
    if type(seconds) is not int or seconds not in (900, 3600):
        raise EnergyDataError("Unsupported interval grid")
    count = (stop - left).total_seconds() / seconds
    if not count.is_integer() or not 1 <= count <= 35136:
        raise EnergyDataError("Invalid bounded measurement window")
    grouped = {}
    for i, record in enumerate(observations):
        if not isinstance(record, dict) or not isinstance(record.get("entity_id"), str):
            raise EnergyDataError("Original sensor identity missing")
        grouped.setdefault(record["entity_id"], []).append((i, record))
    metrics, series = config["metrics"], {}
    for spec in metrics.values():
        for source in spec["sources"]:
            series[id(source)] = _series(grouped.get(source["entity_id"], []), source, config, now)
    rows = []
    for _ in range(int(count)):
        right = left + timedelta(seconds=seconds)
        values, quality = {}, {}
        for name, spec in metrics.items():
            if name == "soc_percent":
                for label, at in (("soc_start_percent", left), ("soc_end_percent", right)):
                    values[label], quality[label] = _metric(name, spec, series, config, at, at, point=True)
                    ids = quality[label].get("records", [])
                    values[label.replace("percent", "at_utc")] = (
                        timestamp(observations[ids[0]]["at"], config).isoformat() if ids else None)
                    rejected = quality[label].get("rejected_candidates", [])
                    if not ids and rejected and rejected[0].get("observed_at_utc"):
                        values[label.replace("percent", "at_utc")] = rejected[0]["observed_at_utc"]
                    point_at = values[label.replace("percent", "at_utc")]
                    values[label.replace("percent", "age_seconds")] = (
                        (at - timestamp(point_at, config)).total_seconds() if point_at else None)
            else:
                values[name], quality[name] = _metric(name, spec, series, config, left, right)
        components = config["load_components"]
        values["load_wh"] = (math.fsum(values[k] for k in components)
                             if all(values[k] is not None for k in components) else None)
        quality["load_wh"] = {"status": "derived_sum" if values["load_wh"] is not None else "incomplete",
                              "components": components}
        # Effective retail rate from measured cost/energy is energy weighted, never
        # an unweighted hourly average. Negative prices/costs remain meaningful.
        if values.get("import_eur_kwh") is None:
            cost, energy = values.get("grid_cost_eur"), values.get("grid_import_wh")
            values["import_eur_kwh"] = cost * 1000 / energy if cost is not None and energy else None
            quality["import_eur_kwh"] = {"status": "derived_energy_weighted_cost" if energy and cost is not None
                                         else "incomplete", "zero_import_rate_invented": False}
        if values.get("grid_cost_eur") is None and values.get("import_eur_kwh") is not None:
            energy = values.get("grid_import_wh")
            values["grid_cost_eur"] = (energy / 1000 * values["import_eur_kwh"]
                                        if energy is not None else None)
            quality["grid_cost_eur"] = {"status": "derived_retail_tariff" if energy is not None else "incomplete"}
        site, error = site_balance(values)
        values["balanced_load_wh"], values["site_balance_error_wh"] = site, error
        missing = [k for k in (*REQUIRED, "soc_start_percent", "soc_end_percent") if values.get(k) is None]
        issues = ["missing:" + k for k in missing]
        if all(values.get(k) is not None for k in ("grid_cost_eur", "grid_import_wh", "import_eur_kwh")):
            if abs(values["grid_cost_eur"] - values["grid_import_wh"] / 1000 * values["import_eur_kwh"]) > .01:
                issues.append("measured_cost_and_tariff_disagree")
        if error is not None and abs(error) > config.get("site_balance_tolerance_wh", 50):
            issues.append("site_balance_exceeds_tolerance")
        if right > now:
            issues.append("interval_not_complete_at_watermark")
        # Stable provenance across arrival ordering and repeated history windows.
        for entry in quality.values():
            for detail in [entry, *entry.get("rejected_candidates", [])]:
                if "records" in detail:
                    detail["records"] = sorted({hashlib.sha256(canonical(observations[i])).hexdigest()
                                                for i in detail["records"]})
        rows.append({"start_utc": left.isoformat(), "end_utc": right.isoformat(), **values,
                     "quality": quality, "issues": issues,
                     "status": "incomplete" if missing or right > now else "failed" if issues else "complete"})
        left = right
    aggregate_keys = {k for k in (*metrics, *REQUIRED, "balanced_load_wh", "site_balance_error_wh")
                      if k.endswith("_wh") or k == "grid_cost_eur"}
    totals = {k: (math.fsum(r[k] for r in rows if r.get(k) is not None)
                  if any(r.get(k) is not None for r in rows) else None)
              for k in sorted(aggregate_keys)}
    totals_coverage = {k: sum(r.get(k) is not None for r in rows) for k in totals}
    return {"schema_version": 1, "energy_kind": "prepared_ac_interval_wh",
            "data_kind": config.get("data_kind", "measured"), "timezone": "UTC",
            "source_sha256": hashlib.sha256(canonical(observations)).hexdigest(),
            "mapping_sha256": hashlib.sha256(canonical(config)).hexdigest(),
            "as_of_utc": now.isoformat(), "original_observations": copy.deepcopy(observations),
            "mapping": copy.deepcopy(config), "rows": rows,
            "audit": {"status": "passed" if all(r["status"] == "complete" for r in rows) else "incomplete",
                      "intervals": len(rows), "complete_intervals": sum(r["status"] == "complete" for r in rows),
                      "energy_complete_intervals": sum(all(r.get(k) is not None for k in REQUIRED) for r in rows),
                      "site_balance_failed_intervals": sum("site_balance_exceeds_tolerance" in r["issues"] for r in rows),
                      "soc_complete_intervals": sum(r.get("soc_start_percent") is not None and r.get("soc_end_percent") is not None for r in rows),
                      "totals": totals, "totals_covered_intervals": totals_coverage,
                      "historical_acceptance_passed": False,
                      "message": "Prepared measurements; historical SOC/tariff/model acceptance remains separate"}}


def verify_prepared(data):
    """Recompute rather than trusting saved values or a hand-edited quality flag."""
    if data.get("energy_kind") != "prepared_ac_interval_wh":
        raise EnergyDataError("Not a shared prepared energy export")
    rows = data["rows"]
    checked = prepare(data["original_observations"], data["mapping"],
                      rows[0]["start_utc"], rows[-1]["end_utc"], as_of=data["as_of_utc"])
    if any(checked[k] != data[k] for k in ("rows", "audit", "source_sha256", "mapping_sha256", "data_kind")):
        raise EnergyDataError("Prepared source or quality audit has been modified")
    return checked


def as_actuals(data):
    """Project into the existing PLAN_ACTUAL contract without a second calculation.

    AC flows stay in prepared.json. DC battery quantities are exposed only when
    the corresponding inverter efficiencies are explicitly configured.
    """
    checked = verify_prepared(data)
    if checked["data_kind"] != "measured" or checked["audit"]["status"] != "passed":
        raise EnergyDataError("Plan-Ist export requires complete measured inputs, never synthetic or failed data")
    config = checked["mapping"]
    dc = all(k in config for k in ("inverter_ac_to_dc_efficiency", "inverter_dc_to_ac_efficiency"))
    energy, tariffs, costs, points = [], [], [], {}
    keys = {"load_wh": "load_wh", "base_pv_wh": "pv_wh", "grid_import_wh": "grid_import_wh",
            "grid_export_wh": "grid_export_wh"}
    for r in checked["rows"]:
        identity = {"start_utc": r["start_utc"], "end_utc": r["end_utc"]}
        values = {out: r[key] for key, out in keys.items() if r.get(key) is not None}
        if dc:
            for key, eff, multiply in (("battery_charge_wh", "inverter_ac_to_dc_efficiency", True),
                                       ("battery_discharge_wh", "inverter_dc_to_ac_efficiency", False)):
                if r.get(key) is not None:
                    value = r[key] * efficiency(config, eff) if multiply else r[key] / efficiency(config, eff)
                    values[key.replace("_wh", "_dc_wh")] = value
        energy.append({**identity, **values})
        if r.get("import_eur_kwh") is not None:
            tariffs.append({**identity, "retail_eur_kwh": r["import_eur_kwh"],
                            "source_method": r["quality"]["import_eur_kwh"]["status"]})
        if (r.get("grid_cost_eur") is not None
                and r["quality"]["grid_cost_eur"]["status"] in ("direct", "derived_counter")):
            costs.append({**identity, "grid_cost_eur": r["grid_cost_eur"],
                          "source_method": r["quality"]["grid_cost_eur"]["status"]})
        for label in ("soc_start_", "soc_end_"):
            if r.get(label + "percent") is not None:
                points[r[label + "at_utc"]] = r[label + "percent"]
    return {"schema_version": 1, "energy_kind": "measured_interval_wh",
            "origin": {"kind": "operator_meter_export", "source_artifact_sha256": checked["source_sha256"],
                       "house_load_scope": "whole_site_including_loadpoints", "pv_basis": "ac",
                       "battery_basis": "dc_bus" if dc else "not_converted",
                       "tariff_basis": "retail_final_eur_kwh",
                       "cost_basis": "measured_grid_purchase_eur" if costs else "not_measured",
                       "manufacturer_standard_mode_confirmed": False},
            "energy": energy, "tariffs": tariffs, "costs": costs,
            "soc": [{"at_utc": at, "percent": value} for at, value in sorted(points.items())],
            "measurement_preparation": {"audit": checked["audit"], "data_kind": checked["data_kind"],
                                        "mapping_sha256": checked["mapping_sha256"],
                                        "interval_quality": [{"start_utc": r["start_utc"],
                                            "end_utc": r["end_utc"], "quality": r["quality"]}
                                            for r in checked["rows"]]}}

"""Read existing solutions/claims under a shared lock; emit sanitized JSON/HTML.

Python 3.11 stdlib only. No config reads, API, optimizer, repair or source writes.
Bundle imports are shipped code, never imports from the installed helper image.
"""

import argparse
import fcntl
import hashlib
import json
import math
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MAX_FILE, MAX_ZIP, MAX_PLANS, MAX_SLOTS = 8_000_000, 60_000_000, 64, 672
VERSION = re.compile(r"[0-9a-f]{64}")
CONTROL_FIELDS = {
    "ac_charge": ("AC-Ladefaktor", "factor"), "dc_charge": ("DC-Ladefaktor", "factor"),
    "discharge_allowed": ("Entladung erlaubt", "flag"),
    "battery_grid_export_allowed": ("Batterieexport erlaubt", "flag"),
    "battery_grid_export_factor": ("Batterieexport-Faktor", "factor"),
    "ev_charge_hours_float": ("EV-Ladefaktor", "factor"),
}
MODEL_FIELDS = {
    "battery_soc_per_hour": ("Modellierter Batterie-SoC", "%"),
    "ev_soc_per_hour": ("Modellierter EV-SoC", "%"),
    "grid_consumption_wh_per_hour": ("Modellierter Netzbezug im Originalslot", "Wh"),
    "grid_feed_in_wh_per_hour": ("Modellierte Einspeisung im Originalslot", "Wh"),
    "costs_per_hour": ("Modellkosten im Originalslot", "EUR"),
    "revenue_per_hour": ("Modellerlöse im Originalslot", "EUR"),
    "losses_per_hour": ("Modellverluste im Originalslot", "Wh"),
}
SUMMARY_FIELDS = {"total_costs": ("Gesamte Modellkosten", "EUR"),
                  "total_revenue": ("Gesamte Modellerlöse", "EUR"),
                  "total_balance": ("Modellbilanz", "EUR"), "total_losses": ("Modellverluste", "Wh")}
TAIL_FIELDS = {"ac_charge_factor": ("AC-Ladefaktor", "factor"),
               "dc_charge_allowed": ("DC-Ladung erlaubt", "flag"),
               "discharge_allowed": ("Entladung erlaubt", "flag"),
               "battery_grid_export_factor": ("Batterieexport-Faktor", "factor")}
STATUSES = {"succeeded", "uncertain", "waiting-publication", "ready-dry-run"}


class InspectorError(ValueError):
    pass


def stamp(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(UTC) if dt.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def numeric(value, kind=None):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    if not math.isfinite(value):
        return None
    if kind == "factor" and not 0 <= value <= 1 or kind == "flag" and value not in (0, 1):
        return None
    return value


def read(root, name, limit=MAX_FILE):
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise InspectorError("Datei fehlt, ist zu groß oder kein sicherer regulärer Datensatz.")
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise InspectorError("Datensatz überschreitet die Größenbegrenzung.")
    return raw


def obj(raw):
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise InspectorError("Datensatz ist kein JSON-Objekt.")
    return value


def local(dt, zone):
    return dt.astimezone(zone).strftime("%d.%m.%Y %H:%M %Z (%z)") if dt else None


def times(start, end, zone):
    return {"start_utc": start.isoformat() if start else None, "end_utc": end.isoformat() if end else None,
            "local": local(start, zone), "end_local": local(end, zone)}


def permissions(values):
    labels = []
    for key, label in (("ac_charge", "AC-Ladefaktor gesetzt"), ("dc_charge", "DC-Ladefaktor gesetzt"),
                       ("discharge_allowed", "Entladung freigegeben"),
                       ("battery_grid_export_allowed", "Batterieexport freigegeben"),
                       ("ev_charge_hours_float", "EV-Ladefaktor gesetzt")):
        if values.get(key) is not None and values[key] > 0:
            labels.append(label)
    if not labels:
        labels.append("Keine Hauptfreigabe gesetzt" if all(values.get(k) == 0 for k in (
            "ac_charge", "dc_charge", "discharge_allowed")) else "Nicht bestimmbar")
    return labels


def archived_inputs(root, version, claim, solution_raw, now):
    """Current prices/soc/forecast are NEVER opened as historical substitutes."""
    missing = {"status": "unproven", "message": "Historische Eingabe nicht belegbar", "values": {}}
    directory = root / "genetic-evidence"
    if directory.is_symlink() or not directory.is_dir():
        return missing
    try:
        if __package__:
            from . import historical as validator
        else:
            import historical_validator as validator
        raw = read(directory, version + ".zip", MAX_ZIP)
        manifest, files = validator.unpack(raw)
        if (manifest["event_version"] != version or not isinstance(claim, dict)
                or obj(files["sync-state.json"]).get("events", {}).get(version) != claim
                or files["solution-" + version + ".json"] != solution_raw):
            raise InspectorError("Archiv passt nicht zum ausgewählten Plan.")
        validator.validate(manifest, files, now=now)
        prices, pv = obj(files["prices.json"])["data"], obj(files["forecast.json"])["data"]
        values = {}
        for key, row in prices.items():
            dt, number = stamp(key), numeric(row.get("elecprice_marketprice_wh"))
            if dt and number is not None:
                values.setdefault(dt.isoformat(), {})["price_eur_kwh"] = number * 1000
        for key, row in pv.items():
            dt, number = stamp(key), numeric(row.get("pvforecast_ac_power"))
            if dt and number is not None:
                values.setdefault(dt.isoformat(), {})["pv_w"] = number
        soc = obj(files["soc.json"])
        return {"status": "verified", "message": "Historische Eingaben durch vollständiges Event-Archiv zugeordnet",
                "archive_sha256": hashlib.sha256(raw).hexdigest(), "captured_at_utc": manifest["captured_at_utc"],
                "initial_soc_percent": numeric(soc.get("percent")),
                "soc_source_timestamp": soc.get("source_timestamp") if stamp(soc.get("source_timestamp")) else None,
                "current_freshness_verified": False, "values": values}
    except Exception:
        return {**missing, "message": "Historische Eingabe nicht belegbar: Archiv fehlt oder Zuordnung/Validierung ungültig"}


def parse_plan(root, version, raw, claim, zone, legacy_zone, now):
    solution = obj(raw)
    start = stamp(solution.get("start_solution_datetime"))
    seconds = solution.get("interval_seconds")
    if type(seconds) is not int or seconds not in (900, 3600):
        seconds = None
    flag = solution.get("controls_start_at_now")
    origin = start if flag is True else None
    time_basis = "run_relative" if origin else "unproven"
    if flag is False and start and legacy_zone:
        origin = start.astimezone(legacy_zone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        time_basis = "legacy_midnight_explicit_timezone"
    claim = claim if isinstance(claim, dict) else {}
    claim_status = claim.get("status")
    status = claim_status if isinstance(claim_status, str) and claim_status in STATUSES else "unmatched"
    warnings = []
    if status != "succeeded":
        warnings.append("Kein erfolgreicher zugeordneter Claim; gespeicherte Lösung ist kein Ausführungsnachweis.")
    claim_matches = bool(claim) and stamp(claim.get("start_utc")) == start and claim.get("interval_seconds") == seconds and claim.get("version") == version
    if claim and not claim_matches:
        warnings.append("Claim-Zeitbasis/Version passt nicht zur Lösung. Eingaben bleiben ausgeblendet.")
        inputs = {"status": "unproven", "message": "Historische Eingabe nicht belegbar", "values": {}}
    else:
        inputs = archived_inputs(root, version, claim, raw, now)
    if origin is None or seconds is None:
        warnings.append("Zeitbasis nicht belegbar: Originalindizes bleiben sichtbar, keine erfundenen Slot-Zeiten.")
    arrays = {}
    for key in CONTROL_FIELDS:
        source = solution.get(key)
        if key == "ev_charge_hours_float" and source is None:
            source = solution.get("eautocharge_hours_float")
        if isinstance(source, list) and source:
            if len(source) > MAX_SLOTS:
                raise InspectorError("Plan enthält zu viele Slots.")
            arrays[key] = source
    count = max((len(a) for a in arrays.values()), default=0)
    if any(len(a) != count for a in arrays.values()):
        warnings.append("Steuerarrays sind ungleich lang; fehlende Einträge werden nicht mit 0 ergänzt.")
    result = solution.get("result") if isinstance(solution.get("result"), dict) else {}
    control_h = numeric(claim.get("control_hours")) if claim_matches else None
    tail_h = numeric(claim.get("effective_tail_hours")) if claim_matches else None
    control_end = start + timedelta(hours=control_h) if start and control_h is not None and 0 <= control_h <= 168 else None
    tail_end = control_end + timedelta(hours=tail_h) if control_end and tail_h is not None and 0 <= tail_h <= 168 else None
    rows, invalid = [], 0
    for i in range(count):
        left = origin + timedelta(seconds=i*seconds) if origin and seconds else None
        right = left + timedelta(seconds=seconds) if left else None
        values = {key: numeric(a[i], CONTROL_FIELDS[key][1]) if i < len(a) else None for key, a in arrays.items()}
        invalid += sum(value is None for value in values.values())
        model_index = int((left-start).total_seconds()/seconds) if left and start else None
        model = {}
        if model_index is not None and model_index >= 0:
            for key in MODEL_FIELDS:
                a = result.get(key)
                if isinstance(a, list) and model_index < len(a):
                    model[key] = numeric(a[model_index])
        phase = ("prefix" if left and start and left < start else "control" if left and control_end and left < control_end
                 else "tail" if left and tail_end and left < tail_end else "undeclared")
        quarters = []
        if left and seconds:
            for j in range(seconds//900):
                q = left + timedelta(minutes=j*15)
                quarters.append({**times(q, q+timedelta(minutes=15), zone),
                                 **inputs["values"].get(q.isoformat(), {})})
        rows.append({"source_index": i, **times(left, right, zone), "phase": phase,
                     "controls": values, "model": model, "permissions": permissions(values), "quarters": quarters})
    if invalid:
        warnings.append("Steuerwerte fehlen oder sind ungültig; sie werden als unbekannt angezeigt.")
    summary = {key: numeric(result.get(key)) for key in SUMMARY_FIELDS if key in result}
    terminal = solution.get("terminal_value") if isinstance(solution.get("terminal_value"), dict) else {}
    terminal_summary = {key: numeric(terminal.get(key)) for key in ("battery_energy_wh", "credited_euro", "effective_tail_hours")
                        if key in terminal}
    tail = []
    tail_raw = terminal.get("tail_plan")
    if isinstance(tail_raw, list):
        if len(tail_raw) > MAX_SLOTS:
            raise InspectorError("Tail enthält zu viele Slots.")
        for i, entry in enumerate(tail_raw):
            if not isinstance(entry, dict):
                continue
            offset = numeric(entry.get("hour_from_start"))
            dt = start + timedelta(hours=offset) if start and offset is not None and 0 <= offset <= 336 else None
            tail.append({"source_index": i, **times(dt, dt+timedelta(seconds=seconds) if dt and seconds else None, zone),
                         "controls": {k: numeric(entry.get(k), kind) for k, (_, kind) in TAIL_FIELDS.items()},
                         "soc_start_percentage": numeric(entry.get("soc_start_percentage")),
                         "soc_end_percentage": numeric(entry.get("soc_end_percentage"))})
    starts = solution.get("appliance_starts")
    occupancy = result.get("home_appliance_running")
    device_keys = sorted(set(starts if isinstance(starts, dict) else {})
                         | set(occupancy if isinstance(occupancy, dict) else {}))
    if len(device_keys) > 32:
        raise InspectorError("Zu viele Geräteeinträge.")
    device_numbers = {key: index+1 for index, key in enumerate(device_keys)}
    appliances = []
    if isinstance(starts, dict):
        if len(starts) > 32:
            raise InspectorError("Zu viele Geräteeinträge.")
        for device, dates in sorted(starts.items()):
            if isinstance(dates, list):
                if len(dates) > MAX_SLOTS:
                    raise InspectorError("Zu viele Geräte-Starttermine.")
                for value in dates:
                    dt = stamp(value)
                    if dt:
                        missed = solution.get("appliance_deadline_missed", {})
                        appliances.append({"device": device_numbers[device], "start_utc": dt.isoformat(), "local": local(dt, zone),
                                           "deadline_missed": missed.get(device) if isinstance(missed, dict)
                                           and isinstance(missed.get(device), bool) else None})
    extra = {}
    ev = solution.get("ev_obj") or solution.get("eauto_obj")
    if isinstance(ev, dict):
        for key in ("charge_array", "discharge_array"):
            if isinstance(ev.get(key), list) and len(ev[key]) <= MAX_SLOTS:
                extra["ev_obj."+key] = [numeric(value, "factor" if key == "charge_array" else "flag") for value in ev[key]]
    running = []
    if isinstance(occupancy, dict):
        if len(occupancy) > 32:
            raise InspectorError("Zu viele Geräte-Belegungen.")
        for device, values in sorted(occupancy.items()):
            if isinstance(values, list):
                if len(values) > MAX_SLOTS:
                    raise InspectorError("Zu viele Geräte-Belegungsslots.")
                running.append({"device": device_numbers[device], "values": [v if isinstance(v, bool) else None for v in values],
                                "start_utc": start.isoformat() if start else None, "interval_seconds": seconds})
    inputs.pop("values")
    return {"version": version, "file": "solution-"+version+".json", "solution_sha256": hashlib.sha256(raw).hexdigest(),
            "claim_status": status, "solution_status": "readable",
            "claimed_at_utc": claim.get("claimed_at_utc") if stamp(claim.get("claimed_at_utc")) else None,
            "start_utc": start.isoformat() if start else None, "start_local": local(start, zone),
            "interval_seconds": seconds, "time_basis": time_basis, "source_slots": count,
            "control_hours": control_h, "effective_tail_hours": tail_h, "warnings": warnings,
            "controls": {key: CONTROL_FIELDS[key] for key in arrays}, "rows": rows, "summary": summary,
            "terminal": terminal_summary, "tail": tail, "appliances": appliances,
            "unmapped_ev_arrays": extra, "appliance_running": running,
            "legacy_washingstart": numeric(solution.get("washingstart")), "inputs": inputs}


def collect(source, timezone="Europe/Berlin", legacy_timezone=None, now=None):
    root, zone = Path(source), ZoneInfo(timezone)
    legacy_zone = ZoneInfo(legacy_timezone) if legacy_timezone else None
    now = now or datetime.now(UTC)
    lock = root / "sync.lock"
    if lock.is_symlink() or not lock.is_file():
        raise InspectorError("Vorhandenes sync.lock fehlt; es wird kein Lock angelegt.")
    with lock.open("rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InspectorError("Sync schreibt gerade. Später erneut lesend versuchen; keinen Prozess stoppen.") from None
        warnings = []
        try:
            events = obj(read(root, "sync-state.json")).get("events", {})
            if not isinstance(events, dict):
                raise ValueError()
        except Exception:
            events = {}
            warnings.append("Claims fehlen oder sind ungültig. Lösungen bleiben als nicht zugeordnet sichtbar.")
        try:
            status = obj(read(root, "sync-report.json")).get("event", {}).get("status")
            status = status if status in STATUSES else "unknown"
        except Exception:
            status = "unknown"
        paths = {p.name[9:-5]: p for p in root.glob("solution-*.json") if VERSION.fullmatch(p.name[9:-5])}
        versions = set(paths) | {v for v in events if VERSION.fullmatch(v)}
        if len(versions) > MAX_PLANS:
            raise InspectorError("Zu viele Pläne für einen Report. Private Diagnosekopie eingrenzen, keine Originale löschen.")
        plans, budget = [], 0
        for version in sorted(versions):
            try:
                raw = read(root, "solution-"+version+".json")
                budget += len(raw)
                if budget > 32_000_000:
                    raise InspectorError("Datenbudget überschritten.")
                plan = parse_plan(root, version, raw, events.get(version), zone, legacy_zone, now)
            except Exception:
                claim = events.get(version)
                claim_status = claim.get("status") if isinstance(claim, dict) else None
                claim_status = claim_status if isinstance(claim_status, str) and claim_status in STATUSES else "unmatched"
                plan = {"version": version, "file": "solution-"+version+".json", "claim_status": claim_status,
                        "solution_status": "unreadable",
                        "source_slots": 0, "controls": {}, "rows": [], "summary": {}, "terminal": {}, "tail": [],
                        "appliances": [], "inputs": {"status": "unproven", "message": "Historische Eingabe nicht belegbar"},
                        "warnings": ["Lösung fehlt, ist beschädigt, unsicher oder überschreitet ein Leselimit."],
                        "unmapped_ev_arrays": {}, "appliance_running": []}
            plans.append(plan)
        plans.sort(key=lambda p: (p.get("start_utc") or "", p["version"]), reverse=True)
        return {"schema_version": 1, "read_only": True, "phase": 1, "timezone": timezone,
                "generated_at_utc": now.isoformat(), "latest_sync_status": status, "warnings": warnings,
                "plans": plans, "summary_fields": SUMMARY_FIELDS, "model_fields": MODEL_FIELDS, "tail_fields": TAIL_FIELDS,
                "baseline": "nicht berechnet", "savings": "nicht berechnet"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/output")
    parser.add_argument("--timezone", default="Europe/Berlin")
    parser.add_argument("--legacy-timezone", help="Explicit known source timezone for legacy midnight-prefix arrays")
    parser.add_argument("--format", choices=("html", "json"), default="html")
    args = parser.parse_args()
    try:
        data = collect(args.source, args.timezone, args.legacy_timezone)
        if args.format == "json":
            text = json.dumps(data, ensure_ascii=False, allow_nan=False)
        else:
            if __package__:
                from .plan_view import render
            else:
                from plan_view import render
            text = render(data)
        sys.stdout.buffer.write(text.encode("utf-8"))
    except Exception as exc:
        reason = str(exc) if isinstance(exc, InspectorError) else "Planübersicht nicht verfügbar; keine Quelldateien geändert."
        print(reason, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

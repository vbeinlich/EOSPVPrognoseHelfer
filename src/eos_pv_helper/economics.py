"""Offline cost comparison of saved controls, never an optimizer or live data reader.

Only explicit run-relative inputs embedded in a solution are accepted. A native
replay must reproduce the stored result before any savings number is returned.
"""

import hashlib
import json
import math
from bisect import bisect_right
from datetime import UTC, datetime

MODEL = "eos-native-self-consumption-v1"
MAX_SLOTS = 672
BATTERY = ("capacity_wh", "initial_soc_percentage", "min_soc_percentage",
           "max_soc_percentage", "charging_efficiency", "discharging_efficiency",
           "max_charge_power_w", "levelized_cost_of_storage_kwh")
INVERTER = ("max_power_wh", "ac_to_dc_efficiency", "dc_to_ac_efficiency",
            "max_ac_charge_power_w", "ac_charge_limits_total_charge",
            "dc_to_ac_efficiency_curve", "dc_to_ac_efficiency_reference_load_fraction")
SERIES = {"pv_forecast_wh": "pv_prognose_wh", "total_load": "gesamtlast",
          "electricity_price_per_wh": "strompreis_euro_pro_wh",
          "feed_in_tariff_per_wh": "einspeiseverguetung_euro_pro_wh"}
RESULT = {"grid_consumption_wh_per_hour": "Netzbezug_Wh_pro_Stunde",
          "grid_feed_in_wh_per_hour": "Netzeinspeisung_Wh_pro_Stunde",
          "battery_soc_per_hour": "akku_soc_pro_stunde", "costs_per_hour": "Kosten_Euro_pro_Stunde",
          "revenue_per_hour": "Einnahmen_Euro_pro_Stunde", "losses_per_hour": "Verluste_Pro_Stunde",
          "electricity_price": "Electricity_price", "feed_in_tariff": "Feed_in_tariff"}
TOTALS = {"total_costs": "Gesamtkosten_Euro", "total_revenue": "Gesamteinnahmen_Euro",
          "total_balance": "Gesamtbilanz_Euro", "total_losses": "Gesamt_Verluste"}


class ComparisonError(ValueError):
    """Only fixed, non-private diagnostic messages may cross the UI boundary."""


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ComparisonError("Numerische Eingabe fehlt oder ist ungültig.")
    return value


def vector(value, length=None, *, nonnegative=False):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_SLOTS:
        raise ComparisonError("Historische Zeitreihe fehlt oder ist unvollständig.")
    if length is not None and len(value) != length:
        raise ComparisonError("Historische Zeitreihen haben unterschiedliche Längen.")
    values = [number(v) for v in value]
    if nonnegative and any(v < 0 for v in values):
        raise ComparisonError("PV, Last oder Energie enthält negative Werte.")
    return values


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def field(obj, key, alias):
    if key not in obj:
        raise ComparisonError("Erforderliche Originaleingabe fehlt; keine Rekonstruktion.")
    if alias in obj and obj[alias] != obj[key]:
        raise ComparisonError("Widersprüchliche historische Aliaswerte.")
    return obj[key]


def project(solution):
    """Whitelist numeric model inputs; no device names, config, tokens or endpoints."""
    if not isinstance(solution, dict) or solution.get("controls_start_at_now") is not True:
        raise ComparisonError("Run-relative Zeitbasis ist nicht nachgewiesen.")
    try:
        start = datetime.fromisoformat(solution["start_solution_datetime"].replace("Z", "+00:00"))
        if start.utcoffset() is None:
            raise ValueError()
        start = start.astimezone(UTC).isoformat()
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ComparisonError("Planstart mit Zeitzone fehlt.") from None
    seconds = solution.get("interval_seconds")
    if type(seconds) is not int or seconds not in (900, 3600):
        raise ComparisonError("Nicht unterstütztes Zeitraster.")
    controls = {k: vector(solution.get(k)) for k in ("ac_charge", "dc_charge", "discharge_allowed")}
    count = len(controls["ac_charge"])
    if any(len(v) != count or any(not 0 <= x <= 1 for x in v) for v in controls.values()):
        raise ComparisonError("Steuerarrays sind unvollständig oder ungültig.")
    if any(v not in (0, 1) for v in controls["discharge_allowed"]):
        raise ComparisonError("Ungültige Entladefreigabe.")
    params = solution.get("parameters", {})
    if not isinstance(params, dict):
        raise ComparisonError("Historische Geräteparameter fehlen.")
    if params.get("forecast_interval_seconds") != seconds:
        raise ComparisonError("Eingabe- und Steuerzeitraster passen nicht zusammen.")
    if any(params.get(k) for k in ("ev", "eauto", "dishwasher", "home_appliances")):
        raise ComparisonError("EV oder flexible Verbraucher werden noch nicht unterstützt.")
    if (any(solution.get(k) for k in ("appliance_starts",))
            or any(number(x) != 0 for k in ("battery_grid_export_factor", "battery_grid_export_allowed",
                                           "ev_charge_hours_float", "eautocharge_hours_float")
                   if solution.get(k) for x in vector(solution[k]))):
        raise ComparisonError("Batterieexport oder zusätzliche Verbraucher werden nicht unterstützt.")
    ems = params.get("ems", {})
    arrays = {k: vector(field(ems, k, alias), nonnegative=k in ("pv_forecast_wh", "total_load"))
              for k, alias in SERIES.items()}
    if len({len(v) for v in arrays.values()}) != 1 or len(arrays["total_load"]) < count:
        raise ComparisonError("Historische PV-/Last-/Preisabdeckung fehlt.")
    bat, inv = params.get("pv_battery", {}), params.get("inverter", {})
    if not isinstance(bat, dict) or not isinstance(inv, dict) or not bat or not inv:
        raise ComparisonError("Originale Batterie- oder Wechselrichterparameter fehlen.")
    if not bat.get("device_id") or inv.get("battery_id") != bat["device_id"]:
        raise ComparisonError("Historische Gerätezuordnung ist inkonsistent.")
    if any(k not in bat for k in BATTERY) or any(k not in inv for k in INVERTER):
        raise ComparisonError("Geräteparameter fehlen; keine impliziten Standardwerte.")
    battery = {k: number(bat[k]) for k in BATTERY}
    inverter = {k: inv[k] for k in INVERTER}
    for k in INVERTER:
        if k not in ("ac_charge_limits_total_charge", "dc_to_ac_efficiency_curve"):
            number(inverter[k])
    if type(inverter["ac_charge_limits_total_charge"]) is not bool:
        raise ComparisonError("Ungültige Wechselrichterbegrenzung.")
    # Curves need an independently tested projection/physics contract. Never silently ignore one.
    if inverter["dc_to_ac_efficiency_curve"] is not None:
        raise ComparisonError("Lastabhängige Wechselrichterkurve noch nicht unterstützt.")
    for k in ("charging_efficiency", "discharging_efficiency"):
        if not 0 < battery[k] <= 1:
            raise ComparisonError("Ungültiger Batteriewirkungsgrad.")
    for k in ("ac_to_dc_efficiency", "dc_to_ac_efficiency"):
        if not 0 < inverter[k] <= 1:
            raise ComparisonError("Ungültiger Wechselrichterwirkungsgrad.")
    if (not 0 <= battery["min_soc_percentage"] <= battery["initial_soc_percentage"]
            <= battery["max_soc_percentage"] <= 100 or battery["capacity_wh"] <= 0
            or battery["max_charge_power_w"] <= 0 or inverter["max_power_wh"] <= 0
            or inverter["max_ac_charge_power_w"] < 0 or battery["levelized_cost_of_storage_kwh"] < 0):
        raise ComparisonError("Ungültige SoC-, Leistungs- oder Kostengrenzen.")
    result = solution.get("result", {})
    expected = {k: vector(field(result, k, alias), count) for k, alias in RESULT.items()}
    expected.update({k: number(field(result, k, alias)) for k, alias in TOTALS.items()})
    if expected["electricity_price"] != arrays["electricity_price_per_wh"][:count]:
        raise ComparisonError("Ergebnispreise passen nicht zu den Originaleingaben.")
    if expected["feed_in_tariff"] != arrays["feed_in_tariff_per_wh"][:count]:
        raise ComparisonError("Ergebnisvergütung passt nicht zu den Originaleingaben.")
    terminal = solution.get("terminal_value", {})
    if terminal.get("mode") not in ("TAIL", "AUTO") or not isinstance(terminal.get("curve"), dict):
        raise ComparisonError("Gemeinsame historische Endwertkurve fehlt oder wird nicht unterstützt.")
    if number(terminal.get("control_horizon_hours")) != count * seconds / 3600:
        raise ComparisonError("Endwert und Kontrollhorizont passen nicht zusammen.")
    curve = {k: vector(terminal["curve"].get(k)) for k in ("energy_wh", "value_euro")}
    if (len(curve["energy_wh"]) < 2 or len(curve["energy_wh"]) != len(curve["value_euro"])
            or curve["energy_wh"][0] != 0 or any(b <= a for a, b in zip(
                curve["energy_wh"], curve["energy_wh"][1:]))):
        raise ComparisonError("Ungültige historische Endwertkurve.")
    max_ac = (battery["max_soc_percentage"] - battery["min_soc_percentage"]) / 100 * battery[
        "capacity_wh"] * battery["discharging_efficiency"] * inverter["dc_to_ac_efficiency"]
    if not math.isclose(curve["energy_wh"][-1], max_ac, abs_tol=1e-5):
        raise ComparisonError("Endwertkurve passt nicht zur nutzbaren Batteriekapazität.")
    return {"start_utc": start, "interval_seconds": seconds, "control_slots": count,
            "controls": controls, "series": arrays, "battery": battery, "inverter": inverter,
            "expected": expected, "terminal_curve": curve,
            "expected_terminal_energy_wh": number(terminal.get("battery_energy_wh")),
            "expected_terminal_credit_eur": number(terminal.get("credited_euro"))}


def terminal_value(curve, energy):
    """Same interpolation for BOTH states, no extrapolation and no repeated credit."""
    energy = number(energy)
    x, y = curve["energy_wh"], curve["value_euro"]
    if energy < -1e-6 or energy > x[-1] + 1e-6:
        raise ComparisonError("Endenergie liegt außerhalb der belegten Endwertkurve.")
    energy = min(max(energy, 0), x[-1])
    i = min(max(bisect_right(x, energy)-1, 0), len(x)-2)
    return y[i] + (y[i+1]-y[i]) * (energy-x[i]) / (x[i+1]-x[i])


def account(run, curve):
    slots = run["slots"]
    grid = sum(number(s["grid_cost_eur"]) for s in slots)
    revenue = sum(number(s["feed_in_revenue_eur"]) for s in slots)
    wear = sum(number(s["wear_eur"]) for s in slots)
    credit = terminal_value(curve, run["end_usable_ac_wh"])
    operating = grid - revenue + wear
    return {"grid_cost_eur": grid, "feed_in_revenue_eur": revenue, "wear_eur": wear,
            "operating_cost_eur": operating, "terminal_credit_eur": credit,
            "adjusted_cost_eur": operating-credit,
            "grid_kwh": sum(s["grid_import_wh"] for s in slots)/1000,
            "feed_in_kwh": sum(s["grid_export_wh"] for s in slots)/1000,
            "losses_kwh": sum(s["losses_wh"] for s in slots)/1000,
            "end_soc_percent": run["end_soc_percent"],
            "end_usable_ac_kwh": run["end_usable_ac_wh"]/1000}


def verify_replay(data, run):
    expected = data["expected"]
    for k in RESULT:
        actual = run["result"][k]
        if len(actual) != len(expected[k]) or any(not math.isclose(number(a), b, rel_tol=1e-9,
                abs_tol=1e-5) for a, b in zip(actual, expected[k])):
            raise ComparisonError("Native Wiedergabe weicht vom gespeicherten GENETIC-Ergebnis ab.")
    for k in TOTALS:
        if not math.isclose(number(run["result"][k]), expected[k], rel_tol=1e-9, abs_tol=1e-5):
            raise ComparisonError("Native Kostensummen weichen vom Original ab.")
    for actual, original in ((run["end_usable_ac_wh"], data["expected_terminal_energy_wh"]),
                             (terminal_value(data["terminal_curve"], run["end_usable_ac_wh"]),
                              data["expected_terminal_credit_eur"])):
        if not math.isclose(number(actual), original, rel_tol=1e-9, abs_tol=1e-5):
            raise ComparisonError("Endenergie oder Endwert ist nicht reproduzierbar.")


def compare(data, *, runner=None, scaled_load=False):
    if runner is None:
        if __package__:
            from .economics_native import simulate
        else:
            from economics_native import simulate
        runner = simulate
    genetic = runner(data, baseline=False, load_scale=1)
    verify_replay(data, genetic)

    def pair(scale):
        g = genetic if scale == 1 else runner(data, baseline=False, load_scale=scale)
        b = runner(data, baseline=True, load_scale=scale)
        ga, ba = account(g, data["terminal_curve"]), account(b, data["terminal_curve"])
        saving = ba["adjusted_cost_eur"] - ga["adjusted_cost_eur"]
        return {"baseline": ba, "genetic": ga, "additional_savings_eur": saving,
                "additional_savings_percent": saving / ba["adjusted_cost_eur"] * 100
                if ba["adjusted_cost_eur"] > 1e-9 else None,
                "slots": {"baseline": b["slots"], "genetic": g["slots"]}}

    result = {"status": "calculated", "message": "Prognostizierter Modellvergleich; keine realisierte Ersparnis",
              "model": MODEL, "input_sha256": digest(data), "replay_verified": True,
              "input_binding": "stored_run_parameters", "source_freshness_verified": False,
              "engine": genetic["engine"], "initial_soc_percent": data["battery"]["initial_soc_percentage"],
              "terminal_method": "identical_saved_curve", **pair(1)}
    result["sensitivity"] = ({"status": "calculated", "annual_load_from_kwh": 8000,
        "annual_load_to_kwh": 11251, "load_scale": 11251/8000,
        "annual_configuration_verified": False, "reoptimized_plan": False,
        "terminal_curve_recomputed": False,
        "method": "linear_scaled_saved_load_fixed_controls_and_terminal_curve",
        "message": "Annahmetest: gespeicherte Last × 11251/8000. Unveränderte GENETIC-Freigaben und historische Endwertkurve; kein neu optimierter 11251-kWh-Plan und kein Nachweis der damaligen Jahreslast.",
        **pair(11251/8000)} if scaled_load else {"status": "not_calculated",
        "message": "Nicht berechenbar: kein gesonderter Last-Annahmetest angefordert."})
    return result


def evaluate(solution, *, runner=None, scaled_load=False):
    try:
        return compare(project(solution), runner=runner, scaled_load=scaled_load)
    except Exception as exc:
        return {"status": "not_calculable", "message": "Nicht berechenbar: " + (
            str(exc) if isinstance(exc, ComparisonError) else
            "native EOS-Engine fehlt, ist inkompatibel oder Eingaben sind unvollständig."),
            "replay_verified": False}


def as_solution(data):
    """Invert the numeric whitelist for a private offline export, never recover missing data."""
    count, seconds = data["control_slots"], data["interval_seconds"]
    return {"controls_start_at_now": True, "start_solution_datetime": data["start_utc"],
            "interval_seconds": seconds, **data["controls"],
            "parameters": {"forecast_interval_seconds": seconds, "ems": data["series"],
                "pv_battery": {"device_id": "battery", **data["battery"]},
                "inverter": {"device_id": "inverter", "battery_id": "battery", **data["inverter"]}},
            "result": data["expected"], "terminal_value": {"mode": "AUTO",
                "control_horizon_hours": count*seconds/3600, "curve": data["terminal_curve"],
                "battery_energy_wh": data["expected_terminal_energy_wh"],
                "credited_euro": data["expected_terminal_credit_eur"]}}

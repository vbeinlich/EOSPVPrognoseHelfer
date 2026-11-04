"""Versioned, stdlib-only verification of separately computed native flow sidecars.

Hashes establish consistency with explicit trusted private exports, not signatures.
This module never imports or executes EOS simulation code.
"""

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta

from . import economics
from .economics_native import EOS_REVISION, EXPECTED_SOURCE

CONTRACT = "eos-pv-helper/native-flow-replay-v1"
BASIS = "internal_storage_wh"
PROOF = "posthoc_native_model_replay"
MAX_BYTES = 32_000_000
EXTRA_RESULT = {
    "load_wh_per_hour": "Last_Wh_pro_Stunde",
    "ev_soc_per_hour": "EAuto_SoC_pro_Stunde",
    "home_appliance_wh_per_hour": "Home_appliance_wh_per_hour",
}


class ReplayError(ValueError):
    pass


def canonical(value):
    return economics.canonical(value)


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def seal(value):
    return {**value, "sha256": digest(value)}


def check_seal(value):
    if not isinstance(value, dict) or value.get("sha256") != digest(
        {k: v for k, v in value.items() if k != "sha256"}
    ):
        raise ReplayError("Replay-Sidecar: Hash oder Struktur ungültig.")


def timestamp(value):
    if not isinstance(value, str):
        raise ReplayError("Replay-Zeitbasis fehlt.")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.utcoffset() is None:
        raise ReplayError("Replay-Zeitbasis ohne Zeitzone.")
    return dt.astimezone(UTC)


def number(value, *, nonnegative=False):
    value = economics.number(value)
    if nonnegative and value < 0:
        raise ReplayError("Replay enthält negative Energie.")
    return value


def close(a, b):
    return math.isclose(number(a), number(b), rel_tol=1e-9, abs_tol=1e-6)


def same_summary(a, b):
    """Allow float summation roundoff across producer/reader Python versions."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_summary(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same_summary(x, y) for x, y in zip(a, b))
    if (
        isinstance(a, (int, float))
        and not isinstance(a, bool)
        and isinstance(b, (int, float))
        and not isinstance(b, bool)
    ):
        return close(a, b)
    return type(a) is type(b) and a == b


def verify_extra(solution, values):
    expected = {
        key: solution["result"][key]
        for canonical, alias in EXTRA_RESULT.items()
        for key in (canonical, alias)
        if key in solution["result"]
    }
    if not isinstance(values, dict) or values.keys() != expected.keys():
        raise ReplayError("Zusätzliche native Ergebnisprüfung ist unvollständig.")
    for key, original in expected.items():
        actual = values[key]
        if original is None:
            valid = actual is None
        else:
            valid = (
                isinstance(actual, list)
                and len(actual) == len(original)
                and all(
                    (a is None and b is None) or (a is not None and b is not None and close(a, b))
                    for a, b in zip(actual, original)
                )
            )
        if not valid:
            raise ReplayError("Native Last-/EV-/Gerätereihe weicht vom Original ab.")


def windows(slots, key):
    result = []
    for i, slot in enumerate(slots):
        if slot[key] <= 0:
            continue
        if (
            result
            and result[-1]["last_index"] == i - 1
            and result[-1]["end_utc"] == slot["start_utc"]
        ):
            result[-1].update(
                last_index=i, end_utc=slot["end_utc"], energy_wh=result[-1]["energy_wh"] + slot[key]
            )
        else:
            result.append(
                {
                    "first_index": i,
                    "last_index": i,
                    "start_utc": slot["start_utc"],
                    "end_utc": slot["end_utc"],
                    "energy_wh": slot[key],
                }
            )
    return result


def summarize(slots, capacity):
    keys = (
        "pv_charge_internal_wh",
        "grid_charge_internal_wh",
        "charge_internal_wh",
        "discharge_internal_wh",
    )
    return {
        **{key: sum(s[key] for s in slots) for key in keys},
        "equivalent_full_cycles": sum(s["discharge_internal_wh"] for s in slots) / capacity,
        "charge_windows": windows(slots, "charge_internal_wh"),
        "discharge_windows": windows(slots, "discharge_internal_wh"),
    }


def catalog(plans, *, now=None):
    return seal(
        {
            "contract": CONTRACT,
            "schema_version": 1,
            "created_at_utc": (now or datetime.now(UTC)).isoformat(),
            "plans": plans,
        }
    )


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise ReplayError("Replay-Sidecar überschreitet das Lesebudget.")
    value = json.loads(raw)
    check_seal(value)
    if (
        value.get("contract") != CONTRACT
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or not isinstance(value.get("plans"), list)
        or not 1 <= len(value["plans"]) <= 4096
    ):
        raise ReplayError("Replay-Vertrag oder Version nicht unterstützt.")
    timestamp(value.get("created_at_utc"))
    seen = set()
    for plan in value["plans"]:
        check_seal(plan)
        source = plan.get("source_solution_sha256")
        if (
            not isinstance(source, str)
            or len(source) != 64
            or any(c not in "0123456789abcdef" for c in source)
            or source in seen
        ):
            raise ReplayError("Replay-Quellzuordnung ist ungültig oder doppelt.")
        seen.add(source)
    return value


def find(catalog_value, source_hash):
    if catalog_value is None:
        return None
    # Validate in-memory callers as strictly as file readers.
    value = decode(canonical(catalog_value))
    return next((p for p in value["plans"] if p["source_solution_sha256"] == source_hash), None)


def validate(plan, raw, solution):
    """Re-check byte/input binding, original replay outputs, physics and summaries."""
    check_seal(plan)
    data = economics.project(solution)
    count, seconds = data["control_slots"], data["interval_seconds"]
    proof = {
        "kind": PROOF,
        "historical_measurement": False,
        "historical_execution_proven": False,
        "exact_solver_options_proven": False,
    }
    if (
        plan.get("source_solution_sha256") != hashlib.sha256(raw).hexdigest()
        or plan.get("parameters_sha256") != digest(solution["parameters"])
        or plan.get("projection_sha256") != digest(data)
        or plan.get("energy_basis") != BASIS
        or plan.get("proof") != proof
        or plan.get("interval_seconds") != seconds
        or plan.get("control_slots") != count
        or plan.get("start_utc") != data["start_utc"]
    ):
        raise ReplayError("Replay passt nicht zu Originalbytes, Parametern oder Zeitbasis.")
    engine = plan["engine"]
    if (
        engine.get("expected_source_revision") != EOS_REVISION
        or engine.get("source_sha256") != EXPECTED_SOURCE
        or engine.get("optimizer_invoked") is not False
        or engine.get("simulation") != "GeneticSimulation.simulate"
        or set(engine.get("dependencies", {})) != {"numpy", "scipy", "pydantic"}
        or any(
            not isinstance(v, str) or not 1 <= len(v) <= 100
            for v in engine["dependencies"].values()
        )
    ):
        raise ReplayError("Native Replay-Engine ist nicht belegt.")
    replay = plan["replay"]
    output = {
        "result": replay["result"],
        "end_soc_percent": replay["end_soc_percent"],
        "end_usable_ac_wh": replay["end_usable_ac_wh"],
    }
    if (
        replay.get("verified") is not True
        or replay.get("instrumentation_identical") is not True
        or replay.get("output_sha256") != digest(output)
        or replay.get("uninstrumented_output_sha256") != digest(output)
        or replay.get("tolerance") != {"relative": 1e-9, "absolute": 1e-5}
    ):
        raise ReplayError("Native Replay-Gleichheitsprüfung fehlt oder ist inkonsistent.")
    economics.verify_replay(data, output)
    verify_extra(solution, replay.get("extra_result", {}))
    b, inv = data["battery"], data["inverter"]
    capacity = b["capacity_wh"] * (b["max_soc_percentage"] - b["min_soc_percentage"]) / 100
    if capacity <= 0 or not close(plan["usable_capacity_wh"], capacity):
        raise ReplayError("Nutzbare interne Speicherkapazität ist inkonsistent.")
    slots = plan["slots"]
    if not isinstance(slots, list) or len(slots) != count:
        raise ReplayError("Replay-Intervalle sind unvollständig.")
    start = timestamp(data["start_utc"])
    keys = (
        "pv_charge_dc_input_wh",
        "grid_charge_dc_input_wh",
        "charge_dc_input_wh",
        "pv_charge_internal_wh",
        "grid_charge_internal_wh",
        "charge_internal_wh",
        "discharge_dc_output_wh",
        "discharge_internal_wh",
        "equivalent_full_cycles",
    )
    for i, s in enumerate(slots):
        if (
            s["source_index"] != i
            or s["start_utc"] != (start + timedelta(seconds=i * seconds)).isoformat()
            or s["end_utc"] != (start + timedelta(seconds=(i + 1) * seconds)).isoformat()
        ):
            raise ReplayError("Replay-Intervalle sind verschoben oder doppelt.")
        for k in keys:
            number(s[k], nonnegative=True)
        c, p, g, d = (
            s["charge_internal_wh"],
            s["pv_charge_internal_wh"],
            s["grid_charge_internal_wh"],
            s["discharge_internal_wh"],
        )
        if not all(
            (
                close(p + g, c),
                close(
                    s["charge_dc_input_wh"],
                    s["pv_charge_dc_input_wh"] + s["grid_charge_dc_input_wh"],
                ),
                close(p, s["pv_charge_dc_input_wh"] * b["charging_efficiency"]),
                close(g, s["grid_charge_dc_input_wh"] * b["charging_efficiency"]),
                close(d * b["discharging_efficiency"], s["discharge_dc_output_wh"]),
                close(s["equivalent_full_cycles"], d / capacity),
            )
        ):
            raise ReplayError("Replay-Energiebasis, Herkunft oder Vollzyklen ist inkonsistent.")
        expected_start = data["expected"]["battery_soc_per_hour"][i]
        expected_end = (
            data["expected"]["battery_soc_per_hour"][i + 1]
            if i + 1 < count
            else replay["end_soc_percent"]
        )
        if (
            not close(s["soc_start_percent"], expected_start)
            or not close(s["soc_end_percent"], expected_end)
            or not close(c - d, (expected_end - expected_start) * b["capacity_wh"] / 100)
            or not b["min_soc_percentage"] - 1e-7
            <= s["soc_end_percent"]
            <= b["max_soc_percentage"] + 1e-7
        ):
            raise ReplayError("Replay-Energie passt nicht zum ursprünglichen SoC-Verlauf.")
        if (
            s["pv_charge_dc_input_wh"] > data["series"]["pv_forecast_wh"][i] + 1e-6
            or s["grid_charge_dc_input_wh"] / inv["ac_to_dc_efficiency"]
            > data["expected"]["grid_consumption_wh_per_hour"][i] + 1e-6
        ):
            raise ReplayError("Replay-Herkunft überschreitet die ursprünglichen Eingangsenergien.")
    if not close(
        (replay["end_soc_percent"] - b["min_soc_percentage"])
        / 100
        * b["capacity_wh"]
        * b["discharging_efficiency"]
        * inv["dc_to_ac_efficiency"],
        replay["end_usable_ac_wh"],
    ):
        raise ReplayError("Replay-Endzustand passt nicht zur belegten Endenergie.")
    if not same_summary(plan["summary"], summarize(slots, capacity)):
        raise ReplayError("Replay-Fenster oder Summen sind inkonsistent.")
    return plan

"""PR24 counter-review. Original JSON is input-only; output stays in a private file.

Only fixed native GeneticSimulation.simulate, never optimize_ems or an API call.
"""

import argparse
import hashlib
import json
import math
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from eos_pv_helper import dashboard, economics, economics_native, plan_inspector
from eos_pv_helper.dashboard_view import render


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def inspect_original(path):
    raw = path.read_bytes()
    solution = json.loads(raw)
    key = hashlib.sha256(raw).hexdigest()
    plan = plan_inspector.parse_plan(
        None,
        key,
        raw,
        None,
        ZoneInfo("Europe/Berlin"),
        None,
        datetime.now(UTC),
        archive_lookup=False,
    )
    dashboard.enrich(plan, solution)
    result = solution["result"]
    inventory = {
        "start_utc": plan["start_utc"],
        "source_sha256": key,
        "interval_seconds": plan["interval_seconds"],
        "slots": plan["source_slots"],
        "stored_result_fields": sorted(result),
        "new_flow_fields_present": {k: k in result for k in dashboard.FLOW_KEYS},
        "flow_proof_counts": {
            p: sum(r["flow"]["proof"] == p for r in plan["rows"])
            for p in ("unavailable", "stored_total_only", "stored_source_split")
        },
        "forecast_keys": sorted(plan["rows"][0]["forecast"]),
        "claim_status": plan["claim_status"],
    }
    count = plan["source_slots"]
    ems = solution["parameters"]["ems"]
    inventory["ui_expected"] = {
        "soc": result["battery_soc_per_hour"],
        "price": ems["electricity_price_per_wh"][:count],
        "pv": ems["pv_forecast_wh"][:count],
        "load": ems["total_load"][:count],
    }
    return solution, plan, inventory


def replay(solution):
    from akkudoktoreos.devices.genetic.inverter import Inverter
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization, GeneticSimulation
    from requests.sessions import Session

    def forbidden(*a, **kw):
        raise AssertionError("Optimizer, API and network forbidden in review")

    GeneticOptimization.optimize_ems = forbidden
    Session.request = forbidden

    def audit(name, args):
        if name in ("socket.connect", "socket.getaddrinfo", "subprocess.Popen"):
            forbidden()

    sys.addaudithook(audit)
    data = economics.project(solution)
    raw_results = []
    simulate_method = GeneticSimulation.simulate

    def capture(self, *args, **kwargs):
        result = simulate_method(self, *args, **kwargs)
        raw_results.append(result)
        return result

    GeneticSimulation.simulate = capture
    uninstrumented = economics_native.simulate(data, baseline=False, load_scale=1)
    economics.verify_replay(data, uninstrumented)
    raw_uninstrumented = raw_results[0]
    extra_fields = {}
    for key, native_key in (
        ("load_wh_per_hour", "Last_Wh_pro_Stunde"),
        ("ev_soc_per_hour", "EAuto_SoC_pro_Stunde"),
        ("home_appliance_wh_per_hour", "Home_appliance_wh_per_hour"),
    ):
        original_value = solution["result"].get(key)
        native_value = raw_uninstrumented[native_key]
        if original_value is None or native_value is None:
            extra_fields[key] = original_value is None and native_value is None
        else:
            extra_fields[key] = len(original_value) == len(native_value) and all(
                (a is None and math.isnan(float(b)))
                or (a is not None and math.isclose(a, float(b), rel_tol=1e-9, abs_tol=1e-5))
                for a, b in zip(original_value, native_value)
            )
    count = data["control_slots"]
    trace = {"pv_charge_dc_input_wh": [0.0] * count, "grid_charge_dc_input_wh": [0.0] * count}
    process, grid = Inverter.process_energy, Inverter.charge_battery_from_grid

    def pv_probe(self, generation, consumption, hour, *args, **kwargs):
        before = self.battery._charged_raw_wh_per_slot[hour]
        answer = process(self, generation, consumption, hour, *args, **kwargs)
        trace["pv_charge_dc_input_wh"][hour] += self.battery._charged_raw_wh_per_slot[hour] - before
        return answer

    def grid_probe(self, hour, factor):
        before = self.battery._charged_raw_wh_per_slot[hour]
        answer = grid(self, hour, factor)
        trace["grid_charge_dc_input_wh"][hour] += (
            self.battery._charged_raw_wh_per_slot[hour] - before
        )
        return answer

    Inverter.process_energy, Inverter.charge_battery_from_grid = pv_probe, grid_probe
    try:
        instrumented = economics_native.simulate(data, baseline=False, load_scale=1)
    finally:
        Inverter.process_energy, Inverter.charge_battery_from_grid = process, grid
    GeneticSimulation.simulate = simulate_method
    economics.verify_replay(data, instrumented)
    assert instrumented == uninstrumented, "Read-only tracing changed native results"
    eta_c, eta_d = data["battery"]["charging_efficiency"], data["battery"]["discharging_efficiency"]
    storage_charge, raw_discharge = [], []
    for i, s in enumerate(instrumented["slots"]):
        assert math.isclose(
            trace["pv_charge_dc_input_wh"][i] + trace["grid_charge_dc_input_wh"][i],
            s["battery_charge_dc_wh"],
            abs_tol=1e-7,
        )
        c, d = s["battery_charge_dc_wh"] * eta_c, s["battery_discharge_dc_wh"] / eta_d
        storage_charge.append(c)
        raw_discharge.append(d)
        delta = (
            (s["soc_end_percent"] - s["soc_start_percent"]) / 100 * data["battery"]["capacity_wh"]
        )
        assert math.isclose(c - d, delta, abs_tol=1e-6)
    capacity = (
        data["battery"]["capacity_wh"]
        * (data["battery"]["max_soc_percentage"] - data["battery"]["min_soc_percentage"])
        / 100
    )
    errors = {
        k: max(abs(a - b) for a, b in zip(instrumented["result"][k], data["expected"][k]))
        for k in economics.RESULT
    }
    return {
        "native_replay_matches_original": True,
        "additional_native_fields_match": extra_fields,
        "instrumentation_identical": True,
        "optimizer_invoked": False,
        "historical_request_binding_proven": False,
        "source_fingerprint": instrumented["engine"],
        "max_abs_series_error": errors,
        "pv_charge_dc_input_wh": trace["pv_charge_dc_input_wh"],
        "grid_charge_dc_input_wh": trace["grid_charge_dc_input_wh"],
        "storage_charge_wh": storage_charge,
        "storage_withdrawal_wh": raw_discharge,
        "battery_dc_delivered_wh": [s["battery_discharge_dc_wh"] for s in instrumented["slots"]],
        "same_slot_charge_and_discharge": sum(
            c > 0 and d > 0 for c, d in zip(storage_charge, raw_discharge)
        ),
        "efc_internal_withdrawal": sum(raw_discharge) / capacity,
        "efc_delivered_dc": sum(s["battery_discharge_dc_wh"] for s in instrumented["slots"])
        / capacity,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", action="append", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--html", required=True)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--counterexample-html")
    args = parser.parse_args()
    originals = [Path(p) for p in args.original]
    before = {str(p): digest(p) for p in originals}
    plans, rows = [], []
    for p in originals:
        solution, plan, inventory = inspect_original(p)
        if args.native:
            inventory["replay"] = replay(solution)
        plans.append(plan)
        rows.append(inventory)
    plans.sort(key=lambda p: p["start_utc"], reverse=True)
    report = {
        "dashboard_schema": 1,
        "read_only": True,
        "plans": plans,
        "latest_sync_status": "unknown",
        "checked_at_utc": datetime.now(UTC).isoformat(),
    }
    with Path(args.html).open("x", encoding="utf-8") as handle:
        handle.write(render(dashboard.prepare(report)))
    assert before == {str(p): digest(p) for p in originals}
    with Path(args.output).open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "reviewed_head": "6af922e4e38bb12d49acbaf02bee0b1fd2da27db",
                "original_files_unchanged": True,
                "originals": rows,
            },
            handle,
            indent=2,
        )
    if args.counterexample_html:
        from dashboard_fixture import make

        with tempfile.TemporaryDirectory(prefix="pr24-synthetic-only-") as folder:
            synthetic = dashboard.prepare(dashboard.collect(make(Path(folder) / "source")))
            synthetic["plans"][0]["rows"][0]["flow"] = {
                "charge_wh": 2000,
                "discharge_wh": 0,
                "pv_wh": 1000,
                "grid_wh": 1000,
                "unknown_wh": 0,
                "proof": "stored_source_split",
            }
            with Path(args.counterexample_html).open("x", encoding="utf-8") as handle:
                handle.write(render(synthetic))
    print(
        json.dumps(
            {
                "original_count": len(rows),
                "original_files_unchanged": True,
                "slots": [r["slots"] for r in rows],
                "native_replay": [
                    r.get("replay", {}).get("native_replay_matches_original") for r in rows
                ],
                "dashboard_flow_proofs": [r["flow_proof_counts"] for r in rows],
                "forecast_keys": [r["forecast_keys"] for r in rows],
            }
        )
    )


if __name__ == "__main__":
    main()

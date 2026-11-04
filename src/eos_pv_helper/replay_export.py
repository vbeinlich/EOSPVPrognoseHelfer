"""Explicit offline-only producer for immutable native fixed-control flow sidecars.

Not shipped in the stdlib dashboard bundle; never called by HTML refresh or sync.
"""

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from . import economics, economics_native
from . import replay_contract as contract


def create_plan(raw):
    with tempfile.TemporaryDirectory(prefix="eos-offline-replay-") as folder:
        with patch.dict(os.environ, {"EOS_DIR": folder, "EOS_CONFIG_DIR": folder}):
            return _create_plan(raw)


def _create_plan(raw):
    solution = json.loads(raw)
    data = economics.project(solution)
    from akkudoktoreos.devices.genetic.inverter import Inverter
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization, GeneticSimulation
    from requests.sessions import Session

    def forbidden(*args, **kwargs):
        raise contract.ReplayError("Optimierersuche und Netzwerk sind im Offline-Replay gesperrt.")

    captures = []
    simulate_method = GeneticSimulation.simulate

    def capture(self, *args, **kwargs):
        result = simulate_method(self, *args, **kwargs)
        captures.append(result)
        return result

    # Both runs use fixed stored controls. No baseline, search, seed or current config.
    with (
        patch.object(GeneticOptimization, "optimize_ems", forbidden),
        patch.object(Session, "request", forbidden),
        patch.object(GeneticSimulation, "simulate", capture),
    ):
        original = economics_native.simulate(data, baseline=False, load_scale=1)
        economics.verify_replay(data, original)
        pv = [0.0] * data["control_slots"]
        grid = [0.0] * data["control_slots"]
        process, charge_grid = Inverter.process_energy, Inverter.charge_battery_from_grid

        def observe_pv(self, generation, consumption, hour, *args, **kwargs):
            before = self.battery._charged_raw_wh_per_slot[hour]
            result = process(self, generation, consumption, hour, *args, **kwargs)
            pv[hour] += self.battery._charged_raw_wh_per_slot[hour] - before
            return result

        def observe_grid(self, hour, factor):
            before = self.battery._charged_raw_wh_per_slot[hour]
            result = charge_grid(self, hour, factor)
            grid[hour] += self.battery._charged_raw_wh_per_slot[hour] - before
            return result

        with (
            patch.object(Inverter, "process_energy", observe_pv),
            patch.object(Inverter, "charge_battery_from_grid", observe_grid),
        ):
            traced = economics_native.simulate(data, baseline=False, load_scale=1)
        economics.verify_replay(data, traced)
        if original != traced:
            raise contract.ReplayError("Lesende Herkunftserfassung verändert native Ergebnisse.")
    extra_results = []
    for captured in captures:
        values = {}
        for canonical, alias in contract.EXTRA_RESULT.items():
            raw_value = captured[alias]
            value = (
                None
                if raw_value is None
                else [None if math.isnan(float(v)) else float(v) for v in raw_value]
            )
            for key in (canonical, alias):
                if key in solution["result"]:
                    values[key] = value
        contract.verify_extra(solution, values)
        extra_results.append(values)
    if len(extra_results) != 2 or extra_results[0] != extra_results[1]:
        raise contract.ReplayError("Lesende Erfassung verändert zusätzliche Ergebnisreihen.")
    b = data["battery"]
    capacity = b["capacity_wh"] * (b["max_soc_percentage"] - b["min_soc_percentage"]) / 100
    start = datetime.fromisoformat(data["start_utc"])
    seconds = data["interval_seconds"]
    slots = []
    for i, s in enumerate(traced["slots"]):
        if not contract.close(pv[i] + grid[i], s["battery_charge_dc_wh"]):
            raise contract.ReplayError("Native Ladeherkunft ist nicht vollständig erfasst.")
        withdrawal = s["battery_discharge_dc_wh"] / b["discharging_efficiency"]
        slots.append(
            {
                "source_index": i,
                "start_utc": (start + timedelta(seconds=i * seconds)).isoformat(),
                "end_utc": (start + timedelta(seconds=(i + 1) * seconds)).isoformat(),
                "pv_charge_dc_input_wh": pv[i],
                "grid_charge_dc_input_wh": grid[i],
                "charge_dc_input_wh": s["battery_charge_dc_wh"],
                "pv_charge_internal_wh": pv[i] * b["charging_efficiency"],
                "grid_charge_internal_wh": grid[i] * b["charging_efficiency"],
                "charge_internal_wh": s["battery_charge_dc_wh"] * b["charging_efficiency"],
                "discharge_dc_output_wh": s["battery_discharge_dc_wh"],
                "discharge_internal_wh": withdrawal,
                "equivalent_full_cycles": withdrawal / capacity,
                "soc_start_percent": s["soc_start_percent"],
                "soc_end_percent": s["soc_end_percent"],
            }
        )
    output = {k: traced[k] for k in ("result", "end_soc_percent", "end_usable_ac_wh")}
    plan = contract.seal(
        {
            "source_solution_sha256": hashlib.sha256(raw).hexdigest(),
            "parameters_sha256": contract.digest(solution["parameters"]),
            "projection_sha256": contract.digest(data),
            "energy_basis": contract.BASIS,
            "usable_capacity_wh": capacity,
            "start_utc": data["start_utc"],
            "interval_seconds": seconds,
            "control_slots": data["control_slots"],
            "engine": traced["engine"],
            "proof": {
                "kind": contract.PROOF,
                "historical_measurement": False,
                "historical_execution_proven": False,
                "exact_solver_options_proven": False,
            },
            "replay": {
                **output,
                "extra_result": extra_results[0],
                "verified": True,
                "instrumentation_identical": True,
                "output_sha256": contract.digest(output),
                "uninstrumented_output_sha256": contract.digest(output),
                "tolerance": {"relative": 1e-9, "absolute": 1e-5},
            },
            "slots": slots,
            "summary": contract.summarize(slots, capacity),
        }
    )
    return contract.validate(plan, raw, solution)


def export(paths, output):
    if not 1 <= len(paths) <= 4096:
        raise contract.ReplayError("Ungültige Anzahl von Originallösungen.")
    originals = [Path(p) for p in paths]
    for p in originals:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 8_000_000:
            raise contract.ReplayError("Unsichere oder zu große Originallösung.")
    originals = [p.resolve(strict=True) for p in originals]
    target = Path(output)
    if target.resolve() in originals or target.exists() or target.is_symlink():
        raise contract.ReplayError("Replay-Ziel muss eine neue separate Datei sein.")
    before = {
        p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in originals
    }
    plans = []
    for p in originals:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > 8_000_000:
            raise contract.ReplayError("Unsichere oder zu große Originallösung.")
        plans.append(create_plan(p.read_bytes()))
    if before != {
        p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in originals
    }:
        raise contract.ReplayError("Originale wurden während des Replays verändert.")
    value = contract.catalog(plans)
    raw = contract.canonical(value)
    contract.decode(raw)
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution", action="append", required=True)
    parser.add_argument("--output", required=True, help="NEW private immutable sidecar file")
    args = parser.parse_args()

    def block_network(name, args):
        if name in ("socket.connect", "socket.getaddrinfo"):
            raise contract.ReplayError("Netzwerk ist im Offline-Exporter gesperrt.")

    __import__("sys").addaudithook(block_network)
    try:
        value = export(args.solution, args.output)
        print(
            json.dumps(
                {
                    "plans": len(value["plans"]),
                    "sha256": hashlib.sha256(contract.canonical(value)).hexdigest(),
                    "optimizer_invoked": False,
                    "energy_basis": contract.BASIS,
                }
            )
        )
        return 0
    except Exception:
        print(
            "Offline-Replay abgelehnt; Originale unverändert, kein Sidecar freigegeben.",
            file=__import__("sys").stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Create synthetic fixed-control replay fixtures and HTML; no optimizer search."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from eos_pv_helper import dashboard, economics, economics_native, replay_export

ROOT = Path(__file__).resolve().parents[1]


def build(destination, *, seconds=3600, start=None):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from requests.sessions import Session

    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    solution = json.loads((ROOT / "tests/fixtures/economics-hold.json").read_text())
    if seconds == 900:
        for key, value in solution["parameters"]["ems"].items():
            if isinstance(value, list):
                solution["parameters"]["ems"][key] = [x for x in value for _ in range(4)]
        for key, value in solution["result"].items():
            if isinstance(value, list):
                solution["result"][key] = [x for x in value for _ in range(4)]
        solution["ac_charge"] = [0] * 96
        solution["dc_charge"] = [1] * 96
    count = len(solution["ac_charge"])
    factor = seconds / 3600
    solution["interval_seconds"] = seconds
    solution["parameters"]["forecast_interval_seconds"] = seconds
    solution["terminal_value"]["control_horizon_hours"] = count * factor
    if start:
        solution["start_solution_datetime"] = start
    solution["parameters"]["ems"]["total_load"] = [
        v * factor for v in solution["parameters"]["ems"]["total_load"]
    ]
    solution["synthetic_only"] = True
    solution["parameters"]["pv_battery"]["device_id"] = "synthetic-battery"
    solution["parameters"]["inverter"]["battery_id"] = "synthetic-battery"
    solution["parameters"]["inverter"]["device_id"] = "synthetic-inverter"
    b = solution["parameters"]["pv_battery"]
    inv = solution["parameters"]["inverter"]
    b.update(charging_efficiency=0.9, discharging_efficiency=0.85)
    inv.update(ac_to_dc_efficiency=0.95, dc_to_ac_efficiency=0.92)
    solution["ac_charge"] = [0.5, 0] + [0] * (count - 2)
    solution["discharge_allowed"] = [1] * count
    solution["parameters"]["ems"]["pv_forecast_wh"] = [3000 * factor, 2000 * factor] + [0] * (
        count - 2
    )
    bound = (
        b["capacity_wh"]
        * (b["max_soc_percentage"] - b["min_soc_percentage"])
        / 100
        * b["discharging_efficiency"]
        * inv["dc_to_ac_efficiency"]
    )
    solution["terminal_value"]["curve"] = {
        "energy_wh": [0, bound],
        "value_euro": [0, bound * 0.0003],
    }

    def forbidden(*a, **kw):
        raise AssertionError("Optimizer/network forbidden in synthetic fixture")

    with (
        patch.object(GeneticOptimization, "optimize_ems", forbidden),
        patch.object(Session, "request", forbidden),
    ):
        native = economics_native.simulate(
            economics.project(solution), baseline=False, load_scale=1
        )
    solution["result"] = native["result"]
    solution["terminal_value"]["battery_energy_wh"] = native["end_usable_ac_wh"]
    solution["terminal_value"]["credited_euro"] = economics.terminal_value(
        solution["terminal_value"]["curve"], native["end_usable_ac_wh"]
    )
    source = root / "solution.json"
    with source.open("x") as handle:
        json.dump(solution, handle)
    sidecar = root / "replays.json"
    replay_export.export([source], sidecar)
    site = root / "site"
    site.mkdir()
    assert dashboard.refresh(None, site, solutions=[source], replay_file=sidecar)
    return {"synthetic_only": True, "optimizer_invoked": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--seconds", type=int, choices=(900, 3600), default=3600)
    parser.add_argument("--start")
    args = parser.parse_args()
    print(json.dumps(build(args.destination, seconds=args.seconds, start=args.start)))

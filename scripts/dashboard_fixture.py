"""Synthetic stored events only. No simulation, network or optimizer."""

import argparse
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


def make(root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "sync.lock").touch()
    events = {}
    for day in range(29, 32):
        start = datetime(2026, 10, day, 12, tzinfo=UTC)
        version = hashlib.sha256(f"synthetic-dashboard-{day}".encode()).hexdigest()
        count, seconds = 96, 900
        pv = [max(0, 600 * (1 - abs(((i + 48) % 96) - 48) / 20)) for i in range(count)]
        charge = [v * 0.65 if v > 100 else (220 if 56 <= i < 68 else 0) for i, v in enumerate(pv)]
        grid = [220 if 56 <= i < 68 and pv[i] <= 100 else 0 for i in range(count)]
        pv_charge = [c - g for c, g in zip(charge, grid)]
        discharge = [90 if c == 0 else 0 for c in charge]
        soc, current = [], 55
        for c, d in zip(charge, discharge):
            soc.append(current)
            current += (c - d) / 130
        price = [
            0.00018 if 56 <= i < 68 else 0.00029 + 0.00008 * (i % 16) / 16 for i in range(count)
        ]
        solution = {
            "synthetic_only": True,
            "start_solution_datetime": start.isoformat(),
            "interval_seconds": seconds,
            "controls_start_at_now": True,
            "ac_charge": [0.5 if g else 0 for g in grid],
            "dc_charge": [1] * count,
            "discharge_allowed": [1 if d else 0 for d in discharge],
            "parameters": {
                "forecast_interval_seconds": seconds,
                "ems": {
                    "pv_forecast_wh": pv,
                    "total_load": [155 + (i % 12) * 3 for i in range(count)],
                    "electricity_price_per_wh": price,
                },
                "pv_battery": {
                    "capacity_wh": 13000,
                    "min_soc_percentage": 10,
                    "max_soc_percentage": 100,
                },
                "password": "PRIVATE-CANARY-192.168.0.123",
            },
            "result": {
                "total_costs": 2.6875 + day - 29,
                "battery_soc_per_hour": soc,
                "grid_consumption_wh_per_hour": [g + 70 for g in grid],
                "battery_flow_energy_basis": "battery_dc",
                "battery_flow_interval_seconds": seconds,
                "battery_flow_start_utc": start.isoformat(),
                "battery_charge_dc_wh_per_hour": charge,
                "battery_discharge_dc_wh_per_hour": discharge,
                "battery_pv_charge_dc_wh_per_hour": pv_charge,
                "battery_grid_charge_dc_wh_per_hour": grid,
            },
        }
        # Third day deliberately includes charge energy with no proven source.
        if day == 31:
            solution["result"].pop("battery_pv_charge_dc_wh_per_hour")
            solution["result"].pop("battery_grid_charge_dc_wh_per_hour")
        events[version] = {
            "version": version,
            "status": "succeeded",
            "start_utc": start.isoformat(),
            "claimed_at_utc": start.isoformat(),
            "control_hours": 24,
            "effective_tail_hours": 10,
            "interval_seconds": seconds,
        }
        (root / f"solution-{version}.json").write_text(json.dumps(solution))
    (root / "sync-state.json").write_text(json.dumps({"events": events}))
    (root / "sync-report.json").write_text('{"event":{"status":"waiting-publication"}}')
    for name in ("prices.json", "forecast.json", "soc.json"):
        (root / name).write_text('{"live_secret":"NEVER-READ"}')
    return root


def event(root, *, hours=1):
    """A new synthetic regular dry-run result arrives, not an optimization call."""
    state = json.loads((root / "sync-state.json").read_text())
    latest = max(state["events"].values(), key=lambda c: c["start_utc"])
    old = latest["version"]
    solution = json.loads((root / f"solution-{old}.json").read_text())
    start = datetime.fromisoformat(latest["start_utc"]) + timedelta(hours=hours)
    version = hashlib.sha256(start.isoformat().encode()).hexdigest()
    state["events"][version] = {
        **copy.deepcopy(latest),
        "version": version,
        "start_utc": start.isoformat(),
        "claimed_at_utc": start.isoformat(),
    }
    solution["start_solution_datetime"] = start.isoformat()
    solution["result"]["battery_flow_start_utc"] = start.isoformat()
    (root / f"solution-{version}.json").write_text(json.dumps(solution))
    (root / "sync-state.json").write_text(json.dumps(state))
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    make(Path(args.destination))

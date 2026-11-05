"""Synthetic committed archive around an already stored fixed-control model result.

Test tooling only: no original/private data, HTTP, optimizer, or native simulation.
"""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from eos_pv_helper import historical, replay_contract

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def create(root, *, day=29):
    root = Path(root)
    root.mkdir(mode=0o700, exist_ok=True)
    solution = json.loads((FIXTURES / "replay-synthetic-solution.json").read_bytes())
    start = datetime(2026, 10, day, 13, tzinfo=UTC)
    claimed = start + timedelta(minutes=5)
    origin = start.astimezone(ZoneInfo("Europe/Berlin")).replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    prices = {"data": {(origin + timedelta(minutes=15*i)).isoformat():
                       {historical.PRICE_KEY: .0003} for i in range(192)}}
    version_info = historical.day_ahead_version(prices, claimed, "Europe/Berlin")
    version = version_info["version"]
    solution["start_solution_datetime"] = start.isoformat()
    solution["parameters"]["pv_battery"]["device_id"] = historical.SOC_DEVICE
    solution["parameters"]["inverter"]["battery_id"] = historical.SOC_DEVICE
    claim = {**version_info, "start_utc": start.isoformat(), "claimed_at_utc": claimed.isoformat(),
             "control_hours": 24, "effective_tail_hours": 0, "interval_seconds": 3600,
             "status": "succeeded"}
    soc = {"usable": True, "source": "evcc", "freshness_verified": True,
           "source_timestamp": claimed.isoformat(), "percent": 40, "factor": .4,
           "timestamp_kind": "successful_uncached_device_read_lower_bound",
           "freshness_evidence": {"contract": "evcc-0.318.1/e3dc-rscp/uncached-getters",
                                  "live_soc_percent": 40, "live_power_w": 0,
                                  "read_started_at_utc": claimed.isoformat(),
                                  "read_completed_at_utc": claimed.isoformat()}}
    pv_values = solution["parameters"]["ems"]["pv_forecast_wh"]
    forecast = {"data": {}}
    for i in range(288):
        dt = origin + timedelta(minutes=15*i)
        index = int((dt-start).total_seconds() // 3600)
        forecast["data"][dt.isoformat()] = {"pvforecast_ac_power": (
            pv_values[index] if start <= dt < start+timedelta(hours=24) else 0)}
    pv = {"checked_at_utc": claimed.isoformat(), "count": 288, "import_verified": True,
          "start_utc": origin.isoformat(), "end_exclusive_utc": (origin+timedelta(hours=72)).isoformat(),
          "source_fetched_at_utc": claimed.isoformat(), "source_max_age_seconds": 3600}
    request = {"soc": {historical.SOC_DEVICE: 40}, "forecasts": {
        "electricity_price_per_wh": [.0003] * (int((start-origin).total_seconds()/3600)+24)}}
    event = {**claim, "request_binding": {
        "contract": historical.BINDING_CONTRACT, "timezone": "Europe/Berlin",
        "origin_utc": origin.isoformat(), "request": request,
        "request_sha256": historical.canonical_sha(request)}}
    state = {"pv_import_verified": True, "events": {version: claim}}
    report = {"checked_at_utc": claimed.isoformat(), "mode": "write", "errors": {},
              "pv": pv, "prices": {"count": 192, "unit": "EUR/Wh", "import_verified": True,
                                     "control_coverage": {"control_complete": True,
                                                          "required_control_hours": 24}},
              "soc": {**soc, "import_verified": True}, "event": event}
    values = {"sync-state.json": state, "sync-report.json": report, "prices.json": prices,
              "soc.json": soc, "forecast.json": forecast, "report.json": pv,
              "solution-" + version + ".json": solution}
    files = {name: (json.dumps(value, indent=2, allow_nan=False)+"\n").encode()
             for name, value in values.items()}
    observed = {"scope": "synthetic_test_only_not_atomic_solver_options"}
    manifest = {"schema_version": 2, "event_version": version,
                "captured_at_utc": claimed.isoformat(), "timezone": "Europe/Berlin",
                "configured_constraints_read": True,
                "validation_constraints": {"max_age_seconds": 300, "max_abs_power_w": 20000},
                "files": {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()},
                "producer": {"contract": "eos-pv-helper/automatic-evidence-v1",
                             "observed_options": observed,
                             "observed_options_sha256": historical.canonical_sha(observed),
                             "solution_inputs": historical.solution_inputs(solution),
                             "dispatched_request_sha256": historical.canonical_sha(request)}}
    assert historical.validate(manifest, files, now=claimed)["accepted"]
    (root / "sync.lock").touch(exist_ok=True)
    old_state = json.loads((root / "sync-state.json").read_bytes()) if (
        root / "sync-state.json").exists() else {"events": {}}
    state["events"].update(old_state["events"])
    for name in ("sync-state.json", "sync-report.json", "solution-" + version + ".json"):
        (root / name).write_bytes((json.dumps(state)+"\n").encode() if name == "sync-state.json"
                                 else files[name])
    archives = root / "genetic-evidence"
    archives.mkdir(mode=0o700, exist_ok=True)
    archive = historical.pack(manifest, files)
    with (archives / (version + ".zip")).open("xb") as handle:
        handle.write(archive)
    # Adapt only synthetic hash/time bindings. Numerical model results stay unchanged.
    sidecar = json.loads((FIXTURES / "replay-synthetic-sidecar.json").read_bytes())
    plan = copy.deepcopy(sidecar["plans"][0])
    raw = files["solution-" + version + ".json"]
    plan["source_solution_sha256"] = hashlib.sha256(raw).hexdigest()
    plan["parameters_sha256"] = replay_contract.digest(solution["parameters"])
    from eos_pv_helper import economics

    data = economics.project(solution)
    plan["projection_sha256"] = replay_contract.digest(data)
    plan["start_utc"] = start.isoformat()
    for i, slot in enumerate(plan["slots"]):
        slot.update(start_utc=(start+timedelta(hours=i)).isoformat(),
                    end_utc=(start+timedelta(hours=i+1)).isoformat())
    plan["summary"] = replay_contract.summarize(plan["slots"], plan["usable_capacity_wh"])
    plan = replay_contract.seal({k: v for k, v in plan.items() if k != "sha256"})
    replay_contract.validate(plan, raw, solution)
    return version, claimed, replay_contract.canonical(replay_contract.catalog([plan]))

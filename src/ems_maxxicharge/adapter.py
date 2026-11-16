"""Transport boundary. The PoC journals SIM messages; it cannot connect to MQTT."""

import re
from dataclasses import dataclass
from typing import Protocol

from .config import SimulationError, number


@dataclass(frozen=True)
class Intent:
    command_id: str
    at_utc: str
    valid_until_utc: str
    discharge_w: float
    grid_charge_w: float


class BatteryAdapter(Protocol):
    def apply_intent(self, intent: Intent) -> dict: ...

    def read_telemetry(self) -> dict: ...


class SimulationAdapter:
    """No publisher/socket/credentials. MQTT envelopes are LOCAL JSON artifacts."""

    def __init__(self, run_id, scenario, max_discharge_w=800, max_grid_charge_w=800):
        if not re.fullmatch("[a-f0-9]{64}", run_id) or not re.fullmatch("[a-z0-9_]+", scenario):
            raise SimulationError("Invalid SIM namespace")
        self.prefix = f"ems/sim/maxxicharge/v1/{run_id}/{scenario}"
        self.max_discharge_w = number(max_discharge_w, "adapter discharge limit", 0)
        self.max_grid_charge_w = number(max_grid_charge_w, "adapter charge limit", 0)
        self._telemetry = None

    def envelope(self, suffix, payload):
        return {"topic": self.prefix + "/" + suffix, "qos": 0, "retain": False,
                "transport": "local_journal_only", "payload": {"schema_version": 1,
                "mode": "SIM", **payload}}

    def apply_intent(self, intent):
        from .inputs import stamp

        number(intent.discharge_w, "intent discharge", 0, self.max_discharge_w)
        number(intent.grid_charge_w, "intent grid charge", 0, self.max_grid_charge_w)
        if (intent.discharge_w > 0 and intent.grid_charge_w > 0
                or stamp(intent.valid_until_utc) <= stamp(intent.at_utc)):
            raise SimulationError("Conflicting or expired SIM intent")
        return self.envelope("intent", {**intent.__dict__, "accepted_in_simulation": True})

    def telemetry(self, state):
        allowed = ("start_utc", "end_utc", "soc_percent", "charge_pv_w", "charge_grid_w",
                   "discharge_w", "end_wh")
        self._telemetry = self.envelope("telemetry", {k: state[k] for k in allowed if k in state})
        return self.read_telemetry()

    def read_telemetry(self):
        if self._telemetry is None:
            raise SimulationError("No SIM telemetry observed yet")
        return {**self._telemetry, "payload": dict(self._telemetry["payload"])}


def journal(report):
    for scenario_id, scenario in report["scenarios"].items():
        cfg = scenario["maxxi_config"]
        if not cfg:
            continue
        adapter = SimulationAdapter(report["run_id"], scenario_id,
                                    cfg["max_discharge_w"], cfg["max_grid_charge_w"])
        for index, row in enumerate(scenario["rows"]):
            state = row["maxxi"]
            yield adapter.apply_intent(Intent(str(index), row["start_utc"], row["end_utc"],
                                              state["discharge_w"], state["charge_grid_w"]))
            yield adapter.telemetry({**state, "start_utc": row["start_utc"],
                                     "end_utc": row["end_utc"]})

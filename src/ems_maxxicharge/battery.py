"""Conservative Wh state model with explicit energy provenance."""

from .config import SimulationError, number

SOURCES = ("base_pv", "extra_pv", "grid", "initial")


class Battery:
    def __init__(self, config):
        self.config = config
        self.reserve = config.capacity_wh * config.min_soc_percent / 100
        self.maximum = config.capacity_wh * config.max_soc_percent / 100
        self.energy = config.capacity_wh * config.initial_soc_percent / 100
        self.pools = dict.fromkeys(SOURCES, 0.0)
        self.pools["initial"] = self.energy - self.reserve
        self.begin()

    @property
    def available(self):
        return max(0, self.energy - self.reserve)

    @property
    def soc(self):
        return self.energy / self.config.capacity_wh * 100

    def begin(self):
        self.flow = {"start_wh": self.energy, "charge_pv_wh": 0.0,
                     "charge_grid_wh": 0.0, "discharge_wh": 0.0,
                     "losses_wh": 0.0, "output_by_source_wh": dict.fromkeys(SOURCES, 0.0)}

    def charge(self, offered_wh, hours, source):
        number(offered_wh, "charge energy", 0)
        number(hours, "interval hours", 1e-9)
        if source not in SOURCES[:3]:
            raise SimulationError("Battery may charge only from PV or grid")
        if self.flow["discharge_wh"] > 1e-9:
            raise SimulationError("Simultaneous charging and discharging forbidden")
        grid = source == "grid"
        key = "charge_grid_wh" if grid else "charge_pv_wh"
        limit = self.config.max_grid_charge_w if grid else self.config.max_pv_charge_w
        total = self.flow["charge_grid_wh"] + self.flow["charge_pv_wh"]
        accepted = max(0, min(offered_wh, limit * hours - self.flow[key],
                              self.config.max_pv_charge_w * hours - total,
                              (self.maximum - self.energy) / self.config.charge_efficiency))
        retained = accepted * self.config.charge_efficiency
        self.energy += retained
        self.pools[source] += retained
        self.flow[key] += accepted
        self.flow["losses_wh"] += accepted - retained
        return accepted

    def discharge(self, demand_wh, hours):
        number(demand_wh, "discharge demand", 0)
        number(hours, "interval hours", 1e-9)
        if self.flow["charge_pv_wh"] + self.flow["charge_grid_wh"] > 1e-9:
            raise SimulationError("Simultaneous charging and discharging forbidden")
        supplied = min(demand_wh,
                       max(0, self.config.max_discharge_w * hours - self.flow["discharge_wh"]),
                       self.available * self.config.discharge_efficiency)
        removed = supplied / self.config.discharge_efficiency
        available = self.available
        for source in SOURCES:
            fraction = self.pools[source] / available if available > 1e-9 else 0
            self.pools[source] -= removed * fraction
            self.flow["output_by_source_wh"][source] += supplied * fraction
        self.energy -= removed
        self.flow["discharge_wh"] += supplied
        self.flow["losses_wh"] += removed - supplied
        return supplied

    def finish(self, hours):
        f = self.flow
        balance = (f["start_wh"] + f["charge_pv_wh"] + f["charge_grid_wh"]
                   - f["discharge_wh"] - f["losses_wh"] - self.energy)
        if (abs(balance) > 1e-6 or self.energy < self.reserve - 1e-6
                or self.energy > self.maximum + 1e-6
                or abs(sum(self.pools.values()) - self.available) > 1e-6):
            raise SimulationError("Battery energy conservation failed")
        return {**f, "end_wh": self.energy, "soc_percent": self.soc,
                "charge_pv_w": f["charge_pv_wh"] / hours,
                "charge_grid_w": f["charge_grid_wh"] / hours,
                "discharge_w": f["discharge_wh"] / hours,
                "balance_error_wh": balance, "stored_by_source_wh": dict(self.pools)}

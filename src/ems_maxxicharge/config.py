"""Explicit simulation assumptions, independent of production EMS configuration."""

import math
from dataclasses import asdict, dataclass, field, replace


class SimulationError(ValueError):
    """Invalid input; do not publish a partially calculated report."""


def number(value, name, low=None, high=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or low is not None and value < low
            or high is not None and value > high):
        raise SimulationError(f"Invalid numeric field: {name}")
    return float(value)


@dataclass(frozen=True)
class BatteryConfig:
    capacity_wh: float = 5000
    min_soc_percent: float = 10
    initial_soc_percent: float = 10
    max_soc_percent: float = 100
    max_discharge_w: float = 800
    max_pv_charge_w: float = 2000
    max_grid_charge_w: float = 800
    charge_efficiency: float = 0.92
    discharge_efficiency: float = 0.92
    wear_eur_per_kwh_output: float = 0

    def __post_init__(self):
        for key, value in asdict(self).items():
            number(value, key, 0)
        if not (self.capacity_wh > 0
                and 0 <= self.min_soc_percent <= self.initial_soc_percent
                <= self.max_soc_percent <= 100
                and 0 < self.charge_efficiency <= 1
                and 0 < self.discharge_efficiency <= 1):
            raise SimulationError("Invalid battery capacity, SOC or efficiency")


@dataclass(frozen=True)
class Panel:
    name: str
    wp: float = 1000
    azimuth_deg: float = 180
    tilt_deg: float = 14
    bifacial_gain: float = 0
    performance_ratio: float = 0.86

    def __post_init__(self):
        if self.name not in ("suedhuette", "suedzaun"):
            raise SimulationError("Unknown panel identity")
        number(self.wp, "wp", 1, 100000)
        number(self.azimuth_deg, "azimuth_deg", 0, 360)
        number(self.tilt_deg, "tilt_deg", 0, 90)
        number(self.bifacial_gain, "bifacial_gain", 0, 1)
        number(self.performance_ratio, "performance_ratio", 0.01, 1)


def construct(cls, values):
    if not isinstance(values, dict):
        raise SimulationError("Configuration section must be an object")
    try:
        return cls(**values)
    except TypeError:
        raise SimulationError("Unknown or missing configuration field") from None


@dataclass(frozen=True)
class Config:
    maxxi: BatteryConfig = field(default_factory=BatteryConfig)
    panels: tuple = field(default_factory=lambda: (
        Panel("suedhuette"), Panel("suedzaun", tilt_deg=90)))
    grid_charging_enabled: bool = True
    lookahead_hours: float = 24
    min_spread_eur_kwh: float = 0.02
    terminal_value_eur_kwh_ac: float = 0.20
    albedo: float = 0.20
    proxy_diffuse_fraction: float = 0.30
    proxy_max_orientation_ratio: float = 3
    representative_year_confirmed: bool = False
    investments_eur: dict = field(default_factory=dict)
    annual_maintenance_eur: dict = field(default_factory=dict)

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.grid_charging_enabled,
                                            self.representative_year_confirmed)):
            raise SimulationError("Simulation switches must be boolean")
        number(self.lookahead_hours, "lookahead_hours", 0.25, 48)
        number(self.min_spread_eur_kwh, "min_spread_eur_kwh", 0)
        number(self.terminal_value_eur_kwh_ac, "terminal_value_eur_kwh_ac", 0)
        number(self.albedo, "albedo", 0, 1)
        number(self.proxy_diffuse_fraction, "proxy_diffuse_fraction", 0, 1)
        number(self.proxy_max_orientation_ratio, "proxy_max_orientation_ratio", 1, 10)
        if len(self.panels) != 2 or {p.name for p in self.panels} != {"suedhuette", "suedzaun"}:
            raise SimulationError("Exactly two distinct panel generators are required")
        for mapping in (self.investments_eur, self.annual_maintenance_eur):
            if not isinstance(mapping, dict) or set(mapping) - set(SCENARIOS):
                raise SimulationError("Unknown investment scenario")
            for value in mapping.values():
                number(value, "investment or annual maintenance", 0)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise SimulationError("Configuration must be an object")
        values = dict(data)
        if "maxxi" in values:
            values["maxxi"] = construct(BatteryConfig, values["maxxi"])
        if "panels" in values:
            if not isinstance(values["panels"], list):
                raise SimulationError("panels must be an array")
            values["panels"] = tuple(construct(Panel, p) for p in values["panels"])
        return construct(cls, values)

    def battery(self, scenario):
        if scenario == "pv2_bat5":
            return self.maxxi
        if scenario == "pv6_bat10":
            return replace(self.maxxi, capacity_wh=self.maxxi.capacity_wh * 2)
        return None


SCENARIOS = {
    "e3dc": ("E3/DC Bestand", 0),
    "pv2_bat5": ("2 kWp PV + 5 kWh Zusatzspeicher", 1),
    "pv6_bat10": ("6 kWp PV + 10 kWh Zusatzspeicher", 3),
    "pv6_only": ("6 kWp zusätzliche PV ohne Zusatzspeicher", 3),
}

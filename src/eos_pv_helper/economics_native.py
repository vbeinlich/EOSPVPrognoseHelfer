"""Pinned EOS forward simulation only. No GENETIC search, API or live configuration.

Imported lazily, so the stdlib-only old-container inspector still works and
explicitly reports a missing engine. Run simulations in an isolated dev container.
"""

import hashlib
import importlib.metadata
from datetime import datetime, timedelta
from pathlib import Path

if __package__:
    from .economics import RESULT, TOTALS, ComparisonError
else:
    from economics import RESULT, TOTALS, ComparisonError

EOS_REVISION = "8a8cd43a1915668927eda5504b7de039c2e762b4"
EXPECTED_SOURCE = {
    "devices/genetic/battery.py": "84b3f78fbc4283d00cb7e3202fe94265376a0c0986520c6f6385a9cca265673e",
    "devices/genetic/inverter.py": "58c51653dc09e942b5a2653cbeb3861235f3c6ecf7ef130ec6b3b21d87954541",
    "devices/devicesabc.py": "1e456514c7c0ccad0bbf305a8a373647bda3f3a2549a179866608430d269dfa4",
    "optimization/genetic/genetic.py": "2258f832b8a9ab3ae8d34902df744582ea56ce5cc7bcd2196760fe46daf513da",
    "optimization/genetic/geneticparams.py": "c56f343efd10c7a7aed45783fb6537c672e60b4a0601e6bec6ce928d052d4ac4",
    "prediction/interpolator.py": "5c3eef23787584bd8565ec4567ca25a09f995ef52d75f60e496ca393abf23bbe",
    "data/regular_grid_interpolator.pkl": "3323bc0e59660699512ddcd1d53e4c1634cc7a8cf9795378fc04765d85bc8dba",
}


def fingerprint(root):
    hashes = {}
    for name in EXPECTED_SOURCE:
        raw = (root/name).read_bytes()
        if name.endswith(".py"):
            raw = raw.replace(b"\r\n", b"\n")
        hashes[name] = hashlib.sha256(raw).hexdigest()
    if hashes != EXPECTED_SOURCE:
        raise ComparisonError("Native EOS-Quelldateien oder PV-/Last-Überlappungstabelle sind ungeprüft.")
    return hashes


def simulate(data, *, baseline, load_scale):
    import akkudoktoreos
    import numpy as np

    hashes = fingerprint(Path(akkudoktoreos.__path__[0]))
    from akkudoktoreos.devices.genetic.battery import Battery, SolarPanelBatteryParameters
    from akkudoktoreos.devices.genetic.inverter import Inverter, InverterParameters
    from akkudoktoreos.optimization.genetic.genetic import GeneticSimulation
    from akkudoktoreos.optimization.genetic.geneticparams import GeneticEnergyManagementParameters

    count, seconds = data["control_slots"], data["interval_seconds"]
    battery = Battery(SolarPanelBatteryParameters.model_validate({"device_id": "battery",
        **data["battery"]}), prediction_hours=count, slot_duration_h=seconds/3600)
    battery.reset()
    inverter = Inverter(InverterParameters.model_validate({"device_id": "inverter", "battery_id": "battery",
        **data["inverter"]}), battery=battery, slot_duration_h=seconds/3600)
    arrays = {k: v[:count] for k, v in data["series"].items()}
    arrays["total_load"] = [v*load_scale for v in arrays["total_load"]]
    arrays["price_per_wh_battery"] = 0  # Not a dispatch input; stored end curve is valued separately.
    simulation = GeneticSimulation()
    simulation.prepare(GeneticEnergyManagementParameters.model_validate(arrays),
        optimization_hours=count*seconds/3600, prediction_hours=count, inverter=inverter,
        direct_marketing_enabled=False)
    for key, target in (("ac_charge", "ac_charge_hours"), ("dc_charge", "dc_charge_hours"),
                        ("discharge_allowed", "bat_discharge_hours")):
        values = np.full(count, 0 if key == "ac_charge" else 1) if baseline else data["controls"][key]
        setattr(simulation, target, np.array(values, dtype=float))
    raw = simulation.simulate(0)
    result = {k: [float(v) for v in raw[alias]] for k, alias in RESULT.items()}
    result.update({k: float(raw[alias]) for k, alias in TOTALS.items()})
    start = datetime.fromisoformat(data["start_utc"])
    slots = []
    for i in range(count):
        imported, exported = result["grid_consumption_wh_per_hour"][i], result["grid_feed_in_wh_per_hour"][i]
        grid_cost = imported*arrays["electricity_price_per_wh"][i]
        wear = battery.discharged_energy_wh(i)*data["battery"]["levelized_cost_of_storage_kwh"]/1000
        if abs(result["costs_per_hour"][i] - grid_cost - wear) > 1e-7:
            raise ComparisonError("Native Verschleißabrechnung passt nicht zum geprüften Vertrag.")
        next_soc = result["battery_soc_per_hour"][i+1] if i+1 < count else battery.current_soc_percentage()
        slots.append({"start_utc": (start+timedelta(seconds=i*seconds)).isoformat(), "interval_seconds": seconds,
            "grid_import_wh": imported, "grid_export_wh": exported, "losses_wh": result["losses_per_hour"][i],
            "soc_start_percent": result["battery_soc_per_hour"][i], "soc_end_percent": next_soc,
            "grid_cost_eur": grid_cost, "wear_eur": wear, "feed_in_revenue_eur": result["revenue_per_hour"][i],
            "pv_wh": arrays["pv_forecast_wh"][i], "load_wh": arrays["total_load"][i],
            "price_eur_kwh": arrays["electricity_price_per_wh"][i]*1000})
    # Fingerprints include the probabilistic intra-slot PV/load-overlap table.
    return {"result": result, "slots": slots, "end_soc_percent": battery.current_soc_percentage(),
            "end_usable_ac_wh": battery.current_energy_content()*inverter.reference_dc_to_ac_efficiency,
            "engine": {"expected_source_revision": EOS_REVISION, "source_sha256": hashes,
                       "dependencies": {k: importlib.metadata.version(k) for k in ("numpy", "scipy", "pydantic")},
                       "simulation": "GeneticSimulation.simulate", "optimizer_invoked": False}}

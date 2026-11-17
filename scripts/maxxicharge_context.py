"""Prepare an explicit geometry/AC proxy from an EXISTING saved EOS config.

Reads only a local file, whitelists location/one plane, never queries EOS. Output
is a modelling assumption and must not be used as proof of meter/PV calibration.
"""

import argparse
import json
from pathlib import Path

from ems_maxxicharge.config import SimulationError, number
from ems_maxxicharge.inputs import canonical, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eos-config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pv-conversion-factor", type=float, required=True)
    parser.add_argument("--acknowledge-proxy", action="store_true", required=True)
    parser.add_argument("--acknowledge-load-scope-assumption", action="store_true", required=True)
    args = parser.parse_args()
    try:
        config, source_sha = read_json(args.eos_config)
        config = config.get("config", config)
        location = config["general"]
        planes = config["pvforecast"]["planes"]
        if not isinstance(planes, list) or len(planes) != 1:
            raise SimulationError("One reference plane required; do not average mixed geometry")
        plane = planes[0]
        proxy = {"mode": "reference_proxy", "proxy_acknowledged": True,
                 "latitude": number(location["latitude"], "latitude", -90, 90),
                 "longitude": number(location["longitude"], "longitude", -180, 180),
                 "reference_wp": number(plane["peakpower"], "reference kWp", .001) * 1000,
                 "reference_tilt_deg": number(plane["surface_tilt"], "reference tilt", 0, 90),
                 "reference_azimuth_deg": number(plane["surface_azimuth"], "reference azimuth", 0, 360),
                 "saved_config_sha256": source_sha}
        context = {"load_scope_model_assumption_acknowledged": True,
                   "pv_conversion_assumption_acknowledged": True,
                   "constant_efficiency_model_acknowledged": True,
                   "pv_conversion_factor_to_ac_equivalent": number(
                       args.pv_conversion_factor, "PV conversion factor", .01, 1),
                   "e3dc_wear_eur_per_kwh_output": 0,
                   "pv_source": proxy}
        with Path(args.output).open("xb") as handle:
            handle.write(canonical(context))
        print(json.dumps({"mode": "SIM", "proxy_assumption": True,
                          "saved_config_sha256": source_sha}))
    except (OSError, SimulationError, KeyError, TypeError, ValueError):
        print("SIM context failed; saved EOS configuration and devices unchanged.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

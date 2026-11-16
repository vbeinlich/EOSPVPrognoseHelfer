"""Reproducible SYNTHETIC weather/load/price fixture. Not installation history."""

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path


def make(days=3, seconds=900):
    start = datetime(2026, 6, 18, tzinfo=UTC)
    rows = []
    for i in range(days * 86400 // seconds):
        at = start + timedelta(seconds=i * seconds)
        hour = at.hour + at.minute / 60
        elevation = max(-15, 60 * math.sin(math.pi * (hour - 5) / 14))
        sun = max(0, math.sin(math.radians(elevation))) if 5 <= hour <= 19 else 0
        load_w = 700 + (1000 if 17 <= hour <= 21 else 0) + (300 if hour < 6 else 0)
        rows.append({"start_utc": at.isoformat(), "end_utc": (at + timedelta(seconds=seconds)).isoformat(),
                     "load_wh": load_w * seconds / 3600,
                     "base_pv_wh": 4000 * sun * seconds / 3600,
                     "import_eur_kwh": 0.10 if hour < 6 else 0.42 if hour >= 17 else 0.26,
                     "export_eur_kwh": 0.08,
                     "weather": {"basis": "interval_mean_w_m2", "ghi": 800 * sun,
                                 "dni": 650 if sun else 0, "dhi": 150 * sun,
                                 "solar_elevation_deg": elevation if sun else -15,
                                 "solar_azimuth_deg": (90 + (hour - 5) * 180 / 14) % 360}})
    return {"schema_version": 1, "energy_basis": "ac_equivalent_wh", "data_kind": "synthetic",
            "source_sha256": [hashlib.sha256(b"synthetic-maxxicharge-fixture-v1").hexdigest()],
            "load_scope": "whole_site_including_loadpoints", "tariff_basis": "retail_final_eur_kwh",
            "pv_source": {"mode": "cached_weather"},
            "e3dc": {"capacity_wh": 13000, "min_soc_percent": 10, "initial_soc_percent": 40,
                      "max_discharge_w": 6000, "max_pv_charge_w": 6000, "max_grid_charge_w": 0,
                      "charge_efficiency": 0.92, "discharge_efficiency": 0.92}, "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    with Path(args.output).open("x", encoding="utf-8") as handle:
        json.dump(make(), handle, ensure_ascii=False, allow_nan=False, indent=2)

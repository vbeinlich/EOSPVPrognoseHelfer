"""Synthetic test fixtures ONLY. Never read live data or manufacture old evidence.

Independent quarter-hour summation, deliberately not the validator's integrator.
Used on the development host; never shipped into the standalone consumer engine.
"""

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def averages(rows, key, origin, count):
    source = {datetime.fromisoformat(k.replace("Z", "+00:00")).astimezone(UTC): v[key] for k, v in rows.items()}
    values = []
    for i in range(count):
        quarter = [source.get(origin+timedelta(hours=i, minutes=15*j)) for j in range(4)]
        values.append(None if None in quarter else sum(quarter)/4)
    return values


def parameters(prices, pv, soc):
    count = len(prices)
    return {"forecast_interval_seconds": 3600,
        "ems": {"pv_forecast_wh": pv, "total_load": [500]*count,
                "electricity_price_per_wh": prices, "feed_in_tariff_per_wh": [.00008]*count},
        "pv_battery": {"device_id": "e3dc_s10e_pro", "capacity_wh": 13000,
            "initial_soc_percentage": soc, "min_soc_percentage": 0, "max_soc_percentage": 100,
            "charging_efficiency": 1, "discharging_efficiency": 1, "max_charge_power_w": 6000,
            "levelized_cost_of_storage_kwh": 0},
        "inverter": {"device_id": "synthetic-inverter", "battery_id": "e3dc_s10e_pro",
            "max_power_wh": 12000, "ac_to_dc_efficiency": 1, "dc_to_ac_efficiency": 1,
            "max_ac_charge_power_w": 6000}}


def bind(values, *, origin=None):
    """Populate already synthetic fixture dictionaries with an independently built receipt."""
    report = values["sync-report.json"]
    report["event"] = copy.deepcopy(report["event"])
    event = report["event"]
    start = datetime.fromisoformat(event["start_utc"])
    if origin is None:
        origin = start.astimezone(ZoneInfo("Europe/Berlin")).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    count = int((start-origin).total_seconds()/3600 + event["control_hours"] + event["effective_tail_hours"])
    prices = averages(values["prices.json"]["data"], "elecprice_marketprice_wh", origin, count)
    assert None not in prices, "Synthetic fixture must supply its own midnight price history"
    payload = {"soc": {"e3dc_s10e_pro": int(values["soc.json"]["percent"])},
               "forecasts": {"electricity_price_per_wh": prices}}
    event["request_binding"] = {"contract": "eos-pv-helper/solver-input-binding-v1",
        "timezone": "Europe/Berlin", "origin_utc": origin.isoformat(),
        "request": payload, "request_sha256": sha(payload)}
    solution = values["solution-" + event["version"] + ".json"]
    solution["controls_start_at_now"] = True
    first = int((start-origin).total_seconds()/3600)
    solution["parameters"] = parameters(prices[first:],
        averages(values["forecast.json"]["data"], "pvforecast_ac_power", origin, count)[first:],
        payload["soc"]["e3dc_s10e_pro"])
    return payload

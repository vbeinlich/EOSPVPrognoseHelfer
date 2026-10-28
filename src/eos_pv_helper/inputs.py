"""Pure input validation. No network, tariff modelling or device control."""

import bisect
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .normalize import ForecastError, timestamp

SOC_KEY = "e3dc_s10e_pro-soc-factor"
PRICE_KEY = "elecprice_marketprice_wh"


def number(value):
    if isinstance(value, bool):
        raise ForecastError("Boolean is not a measurement")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ForecastError("Missing or nonnumeric measurement") from None
    if not math.isfinite(result):
        raise ForecastError("Nonfinite measurement")
    return result


def soc_sample(state, now, max_age=300):
    if state.get("entity_id") != "sensor.evcc_battery_soc":
        raise ForecastError("Unexpected HA SoC entity")
    value = number(state.get("state"))
    if not 0 <= value <= 100:
        raise ForecastError("SoC must be in 0..100 percent")
    # last_changed is NOT the sampling time of an unchanged valid measurement.
    source = state.get("last_reported") or state.get("last_updated")
    if not source:
        raise ForecastError("HA source timestamp missing")
    observed = timestamp(source)
    age = (now - observed).total_seconds()
    if not 0 <= age <= min(max_age, 300):
        raise ForecastError("HA SoC is stale or dated in the future")
    return {"key": SOC_KEY, "source_timestamp": observed.isoformat(),
            "percent": value, "factor": value / 100, "age_seconds": age}


def retail_prices(state):
    """Preserve evcc's complete end price; convert EUR/kWh to EUR/Wh exactly once."""
    if state.get("currency") != "EUR":
        raise ForecastError("evcc price currency must explicitly be EUR")
    rows = state.get("forecast", {}).get("grid")
    if not isinstance(rows, list) or not rows:
        raise ForecastError("evcc forecast.grid is empty")
    data = {}
    for row in rows:
        if not isinstance(row, list) or len(row) != 3:
            raise ForecastError("evcc grid row must be [start, end, EUR/kWh]")
        start, end, price = row
        if (any(isinstance(x, bool) or not isinstance(x, int) for x in (start, end))
                or start % 900 or end - start != 900):
            raise ForecastError("evcc prices must be aligned 900-second intervals")
        number(price)  # Negative end prices are legitimate, NaN/bool are not.
        try:
            converted = float(Decimal(str(price)) / Decimal(1000))
        except InvalidOperation:
            raise ForecastError("Invalid decimal price") from None
        key = datetime.fromtimestamp(start, UTC).isoformat()
        if key in data:
            raise ForecastError("Duplicate evcc price interval")
        data[key] = {PRICE_KEY: converted}
    data = dict(sorted(data.items()))
    stamps = [timestamp(key).timestamp() for key in data]
    if any(b - a != 900 for a, b in zip(stamps, stamps[1:])):
        raise ForecastError("Gap in evcc price intervals")
    return {"data": data, "tz": "UTC"}


def day_ahead_version(frame, now, timezone="Europe/Berlin"):
    """Hash tomorrow's *complete delivery day*, never the sliding forecast window."""
    zone = ZoneInfo(timezone)
    delivery = now.astimezone(zone).date() + timedelta(days=1)
    left = datetime.combine(delivery, datetime.min.time(), zone).astimezone(UTC)
    right = datetime.combine(delivery + timedelta(days=1), datetime.min.time(), zone).astimezone(UTC)
    count = int((right - left).total_seconds() / 900)
    rows = []
    for i in range(count):
        key = (left + timedelta(minutes=15 * i)).isoformat()
        if key not in frame["data"]:
            raise ForecastError("Next delivery day is not yet completely published")
        rows.append([key, frame["data"][key][PRICE_KEY]])
    encoded = json.dumps([delivery.isoformat(), rows], separators=(",", ":")).encode()
    return {"version": hashlib.sha256(encoded).hexdigest(), "delivery_day": str(delivery),
            "delivery_intervals": count}


def raw_series(response):
    data = response.get("data", {})
    if not isinstance(data, dict) or not data:
        raise ForecastError("EOS raw series is empty")
    result = {}
    for key, value in data.items():
        dt = timestamp(key)
        if dt in result:
            raise ForecastError("Duplicate raw-series timestamp")
        result[dt] = None if value is None else number(value)
    return result


def interval_averages(values, start, slots, seconds):
    """Same bounded interval semantics as EOS genetic/forecast.py; never fill gaps."""
    ordered = sorted((key.timestamp(), value) for key, value in values.items())
    if not ordered:
        return [None] * slots
    stamps, samples = zip(*ordered)
    cadence = min([3600] + [b - a for a, b in zip(stamps, stamps[1:])])
    result = []
    for i in range(slots):
        left = start.timestamp() + i * seconds
        right = left + seconds
        position = max(0, bisect.bisect_right(stamps, left) - 1)
        covered, weighted = 0, 0
        while position < len(stamps) and stamps[position] < right:
            end = min(stamps[position] + cadence,
                      stamps[position + 1] if position + 1 < len(stamps) else math.inf)
            overlap = max(0, min(right, end) - max(left, stamps[position]))
            if overlap and samples[position] is not None:
                covered += overlap
                weighted += overlap / seconds * samples[position]
            position += 1
        result.append(weighted if abs(covered - seconds) < 1e-6 else None)
    return result


def coverage(settings, series, now):
    genetic = settings.get("optimization", {}).get("genetic", {})
    seconds = genetic.get("interval_sec")
    control = genetic.get("horizon_hours")
    prediction = settings.get("prediction", {}).get("hours")
    tail = genetic.get("tail_horizon_hours", 0)
    if (any(isinstance(x, bool) or not isinstance(x, int) for x in
            (seconds, control, prediction, tail)) or seconds not in (900, 3600)
            or control < 24 or prediction < control or tail < 0):
        raise ForecastError("Unsupported GENETIC interval/control/prediction horizon")
    zone = ZoneInfo(settings["general"].get("timezone") or
                    settings["general"].get("timezone_override") or "Europe/Berlin")
    midnight = now.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    start = midnight + timedelta(seconds=int((now - midnight).total_seconds() // seconds) * seconds)
    control_slots = control * 3600 // seconds
    budget_tail = min(tail, prediction - control)
    arrays = {}
    for key in ("pvforecast_ac_power", "loadforecast_power_w", PRICE_KEY, "feed_in_tariff_wh"):
        array = interval_averages(series[key], start, prediction * 3600 // seconds, seconds)
        if any(value is None for value in array[:control_slots]):
            raise ForecastError("Incomplete GENETIC control horizon: " + key)
        if key in ("pvforecast_ac_power", "loadforecast_power_w") and any(
            value is not None and value < 0 for value in array
        ):
            raise ForecastError("Negative PV/load forecast")
        arrays[key] = array
    effective = 0
    for i in range(control_slots, control_slots + budget_tail * 3600 // seconds):
        if any(array[i] is None for array in arrays.values()):
            break
        effective += seconds
    return {"start_utc": start.isoformat(), "control_hours": control,
            "interval_seconds": seconds, "requested_tail_hours": tail,
            "budgeted_tail_hours": budget_tail, "effective_tail_hours": effective / 3600}

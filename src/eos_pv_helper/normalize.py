"""Preserve source values and fill only entire solar-night intervals on a UTC grid."""

import math
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from numbers import Real
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import sunrise, sunset

STEP = timedelta(minutes=15)


class ForecastError(ValueError):
    """The forecast cannot safely be used for optimization."""

    def __init__(self, message, *, report=None):
        super().__init__(message)
        self.report = report


def timestamp(value, source_timezone=None):
    """Resolve a timestamp without guessing ambiguous/nonexistent local instants."""
    if not isinstance(value, str):
        raise ForecastError("Timestamp must be an ISO-8601 string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            if not source_timezone:
                raise ForecastError("Naive timestamp requires source.timezone")
            zone = ZoneInfo(source_timezone)
            candidates = set()
            for fold in (0, 1):
                candidate = dt.replace(tzinfo=zone, fold=fold).astimezone(UTC)
                if candidate.astimezone(zone).replace(tzinfo=None) == dt:
                    candidates.add(candidate)
            if len(candidates) != 1:
                raise ForecastError("Ambiguous or nonexistent local timestamp; supply UTC offset")
            return candidates.pop()
        return dt.astimezone(UTC)
    except ForecastError:
        raise
    except (ValueError, TypeError) as exc:
        raise ForecastError("Invalid ISO-8601 timestamp") from exc


def aligned(dt):
    return dt.second == 0 and dt.microsecond == 0 and dt.minute % 15 == 0


def numeric_power(value, unit="W"):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ForecastError("Power must be numeric (null, booleans and numeric strings rejected)")
    if not math.isfinite(value) or value < 0:
        raise ForecastError("Power must be finite and nonnegative")
    if unit not in ("W", "kW"):
        raise ForecastError("Only power in W or kW is supported; energy is not power")
    return value if unit == "W" else value * 1000


def records_from_json(payload, source):
    """Read existing JSON records or EOS series without an external provider call."""
    fmt = source.get("format", "records")
    if fmt == "eos-series":
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            raise ForecastError("EOS series requires an object named data")
        records = [{"timestamp": key, "power": value} for key, value in data.items()]
        time_key, power_key = "timestamp", "power"
    elif fmt == "records":
        records = payload
        for key in source.get("records_path", []):
            if not isinstance(records, dict) or key not in records:
                raise ForecastError("Configured records_path is absent")
            records = records[key]
        time_key = source.get("timestamp_key", "timestamp")
        power_key = source.get("power_key", "power_w")
    else:
        raise ForecastError("Unsupported source format; use records or eos-series")
    if not isinstance(records, list) or not records:
        raise ForecastError("Source forecast is empty or not a list")
    if len(records) > 10000:
        raise ForecastError("Too many source records")
    convention = source.get("timestamp_convention", "start")
    if convention not in ("start", "end"):
        raise ForecastError("timestamp_convention must be start or end")
    values = {}
    for record in records:
        if not isinstance(record, dict) or time_key not in record or power_key not in record:
            raise ForecastError("Source record lacks timestamp or power")
        dt = timestamp(record[time_key], source.get("timezone"))
        if convention == "end":
            dt -= STEP
        if not aligned(dt) and not source.get("allow_irregular_points", False):
            raise ForecastError("Source interval is not aligned to a UTC quarter hour")
        if dt in values:
            raise ForecastError("Duplicate absolute source timestamp")
        values[dt] = numeric_power(record[power_key], source.get("unit", "W"))
    return values


class SolarNight:
    """Night means no overlap with sunrise-to-sunset, computed by Astral locally.

    A boundary interval is NOT night. Unknown/polar solar events fail closed.
    This is solar night, not the narrower astronomical-twilight definition (-18 degrees).
    """

    def __init__(self, latitude, longitude, timezone):
        if not all(isinstance(v, Real) and not isinstance(v, bool) and math.isfinite(v)
                   for v in (latitude, longitude)):
            raise ForecastError("Valid latitude and longitude are required")
        if not -90 < latitude < 90 or not -180 <= longitude <= 180:
            raise ForecastError("Location is outside the valid range")
        self.observer = Observer(latitude=latitude, longitude=longitude)
        self.zone = ZoneInfo(timezone)

    @lru_cache(maxsize=16)
    def events(self, day: date):
        try:
            return (sunrise(self.observer, day, self.zone).astimezone(UTC),
                    sunset(self.observer, day, self.zone).astimezone(UTC))
        except ValueError as exc:
            raise ForecastError("Solar events unavailable; refusing to invent night values") from exc

    def __call__(self, start, end):
        # Include both local dates for an interval spanning local midnight.
        day = start.astimezone(self.zone).date()
        last = end.astimezone(self.zone).date()
        while day <= last:
            rise, setting = self.events(day)
            if start < setting and end > rise:
                return False
            day += timedelta(days=1)
        return True


def normalize(values, start, hours, night, source_interval_seconds=900, *, minimum_hours=None):
    """Validate a fixed horizon or the longest contiguous prefix >= minimum_hours."""
    if start.tzinfo is None:
        raise ForecastError("Horizon start must have a UTC offset")
    start = start.astimezone(UTC)
    if not aligned(start):
        raise ForecastError("Horizon start must be aligned to a quarter hour")
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 168:
        raise ForecastError("Horizon must be an integer between 1 and 168 elapsed hours")
    if minimum_hours is not None and (
        isinstance(minimum_hours, bool) or not isinstance(minimum_hours, int)
        or not 24 <= minimum_hours <= hours
    ):
        raise ForecastError("Dynamic minimum_hours must be an integer >=24 and <= maximum hours")
    if not values:
        raise ForecastError("Empty forecasts cannot be repaired")
    if source_interval_seconds not in (900, 1800, 3600):
        raise ForecastError("Source interval must explicitly be 900, 1800 or 3600 seconds")
    data, filled, missing, interpolated = {}, [], [], []
    known = {dt: numeric_power(value) for dt, value in values.items()}
    if source_interval_seconds > 900:
        # Forecast.Solar publishes power support points, not interval energies.
        # Add only proven whole-night zero anchors, never a daylight zero anchor.
        for index in range(-1, hours * 4 + 1):
            dt = start + index * STEP
            if night(dt, dt + STEP):
                known.setdefault(dt, 0)
    ordered = sorted(known)
    for index in range(hours * 4):
        dt = start + index * STEP
        if dt in values:
            power = numeric_power(values[dt])
        elif night(dt, dt + STEP):
            power = 0
            filled.append(dt.isoformat())
        else:
            position = bisect_right(ordered, dt)
            if source_interval_seconds > 900 and 0 < position < len(ordered):
                left, right = ordered[position - 1], ordered[position]
                gap = (right - left).total_seconds()
                if gap <= source_interval_seconds:
                    fraction = (dt - left).total_seconds() / gap
                    power = known[left] + fraction * (known[right] - known[left])
                    interpolated.append(dt.isoformat())
                else:
                    missing.append(dt.isoformat())
                    if minimum_hours is not None:
                        break
                    continue
            else:
                missing.append(dt.isoformat())
                if minimum_hours is not None:
                    break
                continue
        data[dt.isoformat()] = {"pvforecast_ac_power": power}
    report = {
        "start_utc": start.isoformat(),
        "end_exclusive_utc": (start + len(data) * STEP).isoformat(),
        "interval_seconds": 900,
        "count": len(data),
        "source_count": len(data) - len(filled) - len(interpolated),
        "original_timestamps": [key for key in data if timestamp(key) in values],
        "interpolated_count": len(interpolated),
        "interpolated_timestamps": interpolated,
        "source_interval_seconds": source_interval_seconds,
        "filled_night_count": len(filled),
        "filled_night_timestamps": filled,
        "requested_max_hours": hours,
        "validated_hours": len(data) / 4,
        "minimum_hours": minimum_hours if minimum_hours is not None else hours,
        "first_uncovered_daylight_interval": missing[0] if missing else None,
        "stop_reason": "missing_daylight_interval" if missing else "maximum_reached",
        "tail_available_hours": max(0, len(data) / 4 - (minimum_hours or hours)),
    }
    if missing and (minimum_hours is None or len(data) < minimum_hours * 4):
        if minimum_hours is not None:
            raise ForecastError(f"PV horizon below minimum {minimum_hours} h: only {len(data)/4:g} h; "
                                f"first uncovered daylight interval: {missing[0]}", report=report)
        raise ForecastError(f"Missing {len(missing)} daylight intervals; first: {missing[0]}")
    if not any(start <= dt < start + len(data) * STEP for dt in values):
        raise ForecastError("Source does not overlap the requested forecast horizon")
    return {"data": data, "tz": "UTC"}, report

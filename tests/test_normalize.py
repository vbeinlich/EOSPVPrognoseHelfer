import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from eos_pv_helper.normalize import (
    STEP,
    ForecastError,
    SolarNight,
    normalize,
    records_from_json,
    timestamp,
)


def test_missing_nights_are_zero_and_day_values_unchanged(forecast_case):
    start, night, source = forecast_case
    payload, report = normalize(source, start, 48, night)
    assert len(payload["data"]) == 192
    assert report["filled_night_count"] > 0
    for key, row in payload["data"].items():
        dt = timestamp(key)
        assert row["pvforecast_ac_power"] == source.get(dt, 0)
        if dt not in source:
            assert night(dt, dt + STEP)


def test_daytime_zero_is_preserved(forecast_case):
    start, night, values = forecast_case
    dt = next(iter(values))
    values[dt] = 0
    result, report = normalize(values, start, 48, night)
    assert result["data"][dt.isoformat()]["pvforecast_ac_power"] == 0
    assert dt.isoformat() not in report["filled_night_timestamps"]


def test_day_gap_fails_instead_of_interpolating(forecast_case):
    start, night, values = forecast_case
    values.pop(next(iter(values)))
    with pytest.raises(ForecastError, match="daylight"):
        normalize(values, start, 48, night)


def test_incomplete_second_day_fails(forecast_case):
    start, night, values = forecast_case
    values = {dt: value for dt, value in values.items() if dt < start + timedelta(hours=24)}
    with pytest.raises(ForecastError, match="daylight"):
        normalize(values, start, 48, night)


def test_empty_forecast_cannot_be_repaired(forecast_case):
    start, night, _ = forecast_case
    with pytest.raises(ForecastError, match="Empty"):
        normalize({}, start, 48, night)


def test_interval_containing_sunrise_is_daylight(forecast_case):
    start, night, _ = forecast_case
    rise, setting = night.events(start.astimezone(night.zone).date())
    for event in (rise, setting):
        containing = event.replace(minute=event.minute // 15 * 15, second=0, microsecond=0)
        assert not night(containing, containing + STEP)


@pytest.mark.parametrize("start", ["2026-03-28T00:00:00+01:00", "2026-10-24T00:00:00+02:00"])
def test_dst_48_elapsed_hours_always_have_192_unique_intervals(start):
    start = timestamp(start)
    night = SolarNight(52.52, 13.405, "Europe/Berlin")
    values = {start + i * STEP: i for i in range(192)}
    result, _ = normalize(values, start, 48, night)
    instants = [timestamp(k) for k in result["data"]]
    assert len(set(instants)) == 192
    assert all(b - a == STEP for a, b in zip(instants, instants[1:]))
    offsets = {dt.astimezone(ZoneInfo("Europe/Berlin")).utcoffset() for dt in instants}
    assert len(offsets) == 2


@pytest.mark.parametrize("start,hours,count", [
    ("2026-03-29T00:00:00+01:00", 23, 92),
    ("2026-10-25T00:00:00+02:00", 25, 100),
])
def test_local_dst_calendar_day_is_not_forced_to_96_slots(start, hours, count):
    start = timestamp(start)
    source = {start + i * STEP: 0 for i in range(count)}
    result, _ = normalize(source, start, hours, SolarNight(52.52, 13.405, "Europe/Berlin"))
    assert len(result["data"]) == count
    end = timestamp(list(result["data"])[-1]) + STEP
    assert end.astimezone(ZoneInfo("Europe/Berlin")).hour == 0


def test_repeated_autumn_local_times_are_distinct_when_offset_given():
    a = timestamp("2026-10-25T02:15:00+02:00")
    b = timestamp("2026-10-25T02:15:00+01:00")
    assert b - a == timedelta(hours=1)


@pytest.mark.parametrize("value", ["2026-10-25T02:15:00", "2026-03-29T02:15:00"])
def test_ambiguous_or_nonexistent_naive_local_times_are_rejected(value):
    with pytest.raises(ForecastError, match="Ambiguous or nonexistent"):
        timestamp(value, "Europe/Berlin")


def test_naive_requires_timezone_and_unambiguous_time_can_be_resolved():
    with pytest.raises(ForecastError, match="Naive"):
        timestamp("2026-06-20T12:00:00")
    assert timestamp("2026-06-20T12:00:00", "Europe/Berlin").hour == 10


def test_end_timestamp_kw_conversion_and_record_path():
    result = records_from_json({"forecast": [{"end": "2026-01-01T12:15:00Z", "kw": 1.5}]}, {
        "records_path": ["forecast"], "timestamp_key": "end", "power_key": "kw",
        "timestamp_convention": "end", "unit": "kW",
    })
    assert result == {datetime(2026, 1, 1, 12, tzinfo=UTC): 1500}


def test_eos_series_input():
    assert records_from_json({"data": {"2026-01-01T00:00:00Z": 0}}, {
        "format": "eos-series"
    }) == {datetime(2026, 1, 1, tzinfo=UTC): 0}


@pytest.mark.parametrize("value", [None, True, "12", -1, math.nan, math.inf])
def test_invalid_power_is_not_treated_as_a_missing_night_value(value):
    with pytest.raises(ForecastError):
        records_from_json([{"timestamp": "2026-01-01T00:00:00Z", "power_w": value}], {})


def test_off_grid_and_duplicate_absolute_instants_fail():
    for rows in [
        [{"timestamp": "2026-01-01T00:01:00Z", "power_w": 1}],
        [{"timestamp": "2026-01-01T00:00:00Z", "power_w": 1},
         {"timestamp": "2026-01-01T01:00:00+01:00", "power_w": 1}],
    ]:
        with pytest.raises(ForecastError):
            records_from_json(rows, {})


def test_hourly_daytime_source_is_not_silently_upsampled(forecast_case):
    start, night, source = forecast_case
    hourly = {dt: value for dt, value in source.items() if dt.minute == 0}
    with pytest.raises(ForecastError, match="daylight"):
        normalize(hourly, start, 48, night)


def test_polar_unsupported_events_fail_closed():
    night = SolarNight(89, 0, "UTC")
    with pytest.raises(ForecastError, match="Solar events unavailable"):
        night(datetime(2026, 6, 20, tzinfo=UTC), datetime(2026, 6, 20, 1, tzinfo=UTC))

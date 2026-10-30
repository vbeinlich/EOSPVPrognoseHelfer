from datetime import UTC, datetime, timedelta

import pytest

from eos_pv_helper.app import run_once
from eos_pv_helper.normalize import STEP, ForecastError, SolarNight, normalize, timestamp


@pytest.mark.parametrize("gap", [24, 30.25, 37, 47.75])
def test_dynamic_uses_every_contiguous_quarter_before_day_gap(gap):
    start = datetime(2026, 6, 20, tzinfo=UTC)
    values = {start + i * STEP: 0 if i % 7 == 0 else 1234.567 for i in range(192)}
    values.pop(start + timedelta(hours=gap))
    payload, report = normalize(values, start, 48, lambda *_: False, minimum_hours=24)
    assert report["validated_hours"] == gap
    assert len(payload["data"]) == gap * 4
    assert report["tail_available_hours"] == gap - 24
    assert report["first_uncovered_daylight_interval"] == (start + timedelta(hours=gap)).isoformat()
    assert all(row["pvforecast_ac_power"] == values[timestamp(key)]
               for key, row in payload["data"].items())


def test_day_gap_at_23_hours_fails_with_structured_diagnostic():
    start = datetime(2026, 6, 20, tzinfo=UTC)
    values = {start + i * STEP: 0 for i in range(192) if i != 92}
    with pytest.raises(ForecastError, match="below minimum") as error:
        normalize(values, start, 48, lambda *_: False, minimum_hours=24)
    assert error.value.report["validated_hours"] == 23


@pytest.mark.parametrize("start", ["2026-03-28T06:00:00Z", "2026-10-24T15:00:00Z",
                                  "2026-06-20T04:00:00Z", "2026-10-29T19:00:00Z"])
def test_dynamic_solar_nights_and_dst_are_elapsed_quarters(start):
    start = timestamp(start)
    night = SolarNight(52.52, 13.405, "Europe/Berlin")
    values = {start + i * STEP: 4321.25 for i in range(120)
              if not night(start + i * STEP, start + (i + 1) * STEP)}
    payload, report = normalize(values, start, 48, night, minimum_hours=24)
    assert 24 <= report["validated_hours"] <= 48
    assert report["filled_night_count"] > 0
    instants = [timestamp(k) for k in payload["data"]]
    assert all(right - left == STEP for left, right in zip(instants, instants[1:]))
    for key, row in payload["data"].items():
        dt = timestamp(key)
        if dt not in values:
            assert night(dt, dt + STEP) and row["pvforecast_ac_power"] == 0


@pytest.mark.parametrize("cadence", [900, 1800, 3600])
def test_source_support_cadence_never_bridges_a_missing_day_interval(cadence):
    start = datetime(2026, 6, 20, tzinfo=UTC)
    count = int(37 * 3600 / cadence)
    values = {start + timedelta(seconds=i*cadence): i for i in range(count + 1)}
    payload, report = normalize(values, start, 48, lambda *_: False, cadence, minimum_hours=24)
    expected = 37.25  # A source point is preserved, never extrapolated past its timestamp.
    assert report["validated_hours"] == expected
    assert all(payload["data"][dt.isoformat()]["pvforecast_ac_power"] == value
               for dt, value in values.items())


def test_failed_minimum_does_not_export_or_import_new_forecast(config, tmp_path):
    config["horizon"].update(mode="dynamic", minimum_hours=24, max_hours=48)
    start = timestamp(config["horizon"]["start"])
    # The first interval is daytime at the synthetic location's current date/hour.
    config["horizon"]["start"] = start.replace(hour=12).isoformat()
    with pytest.raises(ForecastError):
        run_once(config, source_reader=lambda _: [{"timestamp": start.isoformat(), "power_w": 0}],
                 http=lambda *a, **k: pytest.fail("No EOS call after invalid minimum"))
    import json
    failure = json.loads((tmp_path / "forecast-error.json").read_text())
    assert failure["ok"] is False and failure["minimum_hours"] == 24
    assert not (tmp_path / "forecast.json").exists()


def test_fixed_app_mode_cannot_bypass_24_hour_minimum(config):
    config["horizon"].update(mode="fixed", hours=23)
    with pytest.raises(ForecastError, match="24..168"):
        run_once(config, source_reader=lambda *_: pytest.fail("Invalid horizon before any source read"))


def test_slow_source_crossing_quarter_realigns_horizon_after_read(config):
    config["horizon"].pop("start")
    initial = datetime(2026, 6, 20, 12, 14, tzinfo=UTC)
    instant = [initial]
    start = initial.replace(hour=0, minute=0)

    def source(_):
        instant[0] += timedelta(minutes=2)
        return [{"timestamp": (start + i * STEP).isoformat(), "power_w": 1000} for i in range(288)]
    _, report = run_once(config, source_reader=source, clock=lambda: instant[0])
    assert report["start_utc"] == initial.replace(minute=15).isoformat()
    assert report["validated_hours"] == 48

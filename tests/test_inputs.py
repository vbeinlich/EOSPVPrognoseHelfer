from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from eos_pv_helper.inputs import (
    PRICE_KEY,
    coverage,
    day_ahead_version,
    interval_averages,
    retail_prices,
    soc_sample,
)
from eos_pv_helper.normalize import ForecastError

NOW = datetime(2026, 10, 28, 12, tzinfo=UTC)


def ha(value="55", **changes):
    return {"entity_id": "sensor.evcc_battery_soc", "state": value,
            "last_updated": NOW.isoformat(), **changes}


@pytest.mark.parametrize("value,factor", [("0", 0), ("55.5", .555), ("100", 1)])
def test_soc_factor_and_source_time(value, factor):
    sample = soc_sample(ha(value), NOW)
    assert sample["factor"] == factor
    assert sample["source_timestamp"] == NOW.isoformat()


@pytest.mark.parametrize("value", ["unknown", "unavailable", None, "nan", "inf", -1, 101, True])
def test_invalid_soc_is_not_replaced(value):
    with pytest.raises(ForecastError):
        soc_sample(ha(value), NOW)


@pytest.mark.parametrize("age", [-1, 301])
def test_stale_or_future_soc(age):
    with pytest.raises(ForecastError, match="stale|future"):
        soc_sample(ha(last_updated=(NOW - timedelta(seconds=age)).isoformat()), NOW)


def test_unchanged_soc_uses_report_time_not_last_changed():
    sample = soc_sample(ha(last_updated="2020-01-01T00:00:00Z",
                           last_changed="2020-01-01T00:00:00Z",
                           last_reported=(NOW - timedelta(seconds=300)).isoformat()), NOW)
    assert sample["age_seconds"] == 300
    assert sample["source_timestamp"] != NOW.isoformat()
    with pytest.raises(ForecastError):
        soc_sample(ha(last_updated=None), NOW)


def grid(start, count=192, value=.30):
    return {"currency": "EUR", "forecast": {"grid": [
        [int(start.timestamp()) + i * 900, int(start.timestamp()) + (i + 1) * 900, value]
        for i in range(count)]}}


@pytest.mark.parametrize("price,expected", [(.30, .0003), (-.14, -.00014), (0, 0)])
def test_retail_conversion_without_fees(price, expected):
    frame = retail_prices(grid(NOW, value=price))
    assert all(row[PRICE_KEY] == expected for row in frame["data"].values())


@pytest.mark.parametrize("change", ["gap", "duplicate", "unaligned", "currency", "nan"])
def test_invalid_price_grids(change):
    data = grid(NOW)
    rows = data["forecast"]["grid"]
    if change == "gap":
        rows.pop(5)
    elif change == "duplicate":
        rows.append(rows[0])
    elif change == "unaligned":
        rows[0][0] += 1
    elif change == "currency":
        data["currency"] = "USD"
    else:
        rows[0][2] = float("nan")
    with pytest.raises(ForecastError):
        retail_prices(data)


@pytest.mark.parametrize("day,expected", [("2026-03-28", 92), ("2026-10-24", 100),
                                         ("2026-10-28", 96)])
def test_delivery_day_hash_handles_dst_and_sliding_windows(day, expected):
    zone = ZoneInfo("Europe/Berlin")
    now = datetime.fromisoformat(day).replace(hour=12, tzinfo=zone).astimezone(UTC)
    source = grid(now - timedelta(hours=10), 240)
    first = day_ahead_version(retail_prices(source), now)
    assert first["delivery_intervals"] == expected
    source["forecast"]["grid"] = source["forecast"]["grid"][4:]
    assert day_ahead_version(retail_prices(source), now)["version"] == first["version"]
    source["forecast"]["grid"][-1][2] = .77  # Outside tomorrow: not a new publication.
    assert day_ahead_version(retail_prices(source), now)["version"] == first["version"]
    source["forecast"]["grid"][110][2] = .88
    assert day_ahead_version(retail_prices(source), now)["version"] != first["version"]


def test_partial_day_ahead_never_triggers():
    with pytest.raises(ForecastError, match="not yet completely"):
        day_ahead_version(retail_prices(grid(NOW, 48)), NOW)


def settings():
    return {"general": {"timezone": "Europe/Berlin"}, "prediction": {"hours": 48},
            "optimization": {"genetic": {"interval_sec": 3600, "horizon_hours": 24,
                                         "tail_horizon_hours": 48}}}


def test_control_24_and_tail_48_is_capped_not_72_hours():
    data = {NOW + timedelta(hours=i): 0.3 for i in range(30)}
    series = {key: data.copy() for key in
              ("pvforecast_ac_power", "loadforecast_power_w", PRICE_KEY, "feed_in_tariff_wh")}
    plan = coverage(settings(), series, NOW)
    assert plan["budgeted_tail_hours"] == 24
    assert plan["effective_tail_hours"] == 6
    series["loadforecast_power_w"].pop(NOW + timedelta(hours=4))
    with pytest.raises(ForecastError, match="loadforecast_power_w"):
        coverage(settings(), series, NOW)


def test_interval_averages_preserve_gaps_and_integrate_quarters():
    values = {NOW + timedelta(minutes=15 * i): i for i in range(8)}
    assert interval_averages(values, NOW, 2, 3600) == [1.5, 5.5]
    values.pop(NOW + timedelta(minutes=75))
    assert interval_averages(values, NOW, 2, 3600) == [1.5, None]
    assert interval_averages({NOW: 0}, NOW, 2, 3600) == [0, None]


@pytest.mark.parametrize("instant,count", [("2026-10-25T02:30:00+02:00", 26),
                                           ("2026-10-25T02:30:00+01:00", 27),
                                           ("2026-03-29T03:30:00+02:00", 26)])
def test_native_price_prefix_uses_elapsed_dst_slots(instant, count):
    from eos_pv_helper.inputs import genetic_window, native_price_runtime
    from eos_pv_helper.normalize import timestamp

    now = timestamp(instant)
    origin = now.astimezone(ZoneInfo("Europe/Berlin")).replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
    values = {origin + timedelta(minutes=i*15): .0003 for i in range(300)}
    start, _, _, _, _, _, _ = genetic_window(settings(), now)
    plan = {"start_utc": start.isoformat(), "control_hours": 24,
            "effective_tail_hours": 0, "interval_seconds": 3600}
    assert len(native_price_runtime(settings(), values, plan, now)) == count


def test_native_price_prefix_never_invents_missing_history():
    from eos_pv_helper.inputs import genetic_window, native_price_runtime

    start, _, _, _, _, _, _ = genetic_window(settings(), NOW)
    values = {NOW + timedelta(minutes=15*i): .0003 for i in range(192)}
    plan = {"start_utc": start.isoformat(), "control_hours": 24,
            "effective_tail_hours": 0, "interval_seconds": 3600}
    with pytest.raises(ForecastError, match="real evcc prices from local midnight"):
        native_price_runtime(settings(), values, plan, NOW)

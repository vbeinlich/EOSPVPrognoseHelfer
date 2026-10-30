from datetime import UTC, datetime, timedelta

import pytest

from eos_pv_helper.inputs import verify_price_readback
from eos_pv_helper.normalize import ForecastError

NOW = datetime(2026, 10, 29, 7, 31, 48, tzinfo=UTC)
START = NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def prices():
    return {(START + timedelta(minutes=i*15)).isoformat(): -.0001 if i % 4 == 0 else .0003
            for i in range(192)}


def test_documented_history_cut_is_not_a_price_import_failure():
    expected = prices()
    observed = {datetime.fromisoformat(k): v for k, v in list(expected.items())[28:]}
    report = verify_price_readback(expected, observed, NOW)
    assert len(report["historical_missing_intervals"]) == 28
    assert report["future_missing_intervals"] == report["mismatched_intervals"] == []


@pytest.mark.parametrize("offset", [30, 33, 96])
def test_missing_current_or_future_interval_remains_an_error(offset):
    expected = prices()
    observed = {datetime.fromisoformat(k): v for k, v in expected.items()}
    missing = START + timedelta(minutes=15*offset)
    observed.pop(missing)
    with pytest.raises(ForecastError) as error:
        verify_price_readback(expected, observed, NOW)
    assert error.value.report["future_missing_intervals"] == [missing.isoformat()]


def test_all_present_history_and_future_prices_must_match_with_defined_tolerance():
    expected = prices()
    observed = {datetime.fromisoformat(k): v + 1e-14 for k, v in expected.items()}
    assert verify_price_readback(expected, observed, NOW)["verified_interval_count"] == 192
    observed[START] += .00001
    with pytest.raises(ForecastError) as error:
        verify_price_readback(expected, observed, NOW)
    assert error.value.report["mismatched_intervals"] == [START.isoformat()]


def test_changed_source_is_compared_against_the_new_prices_not_a_previous_cache():
    expected = prices()
    observed = {datetime.fromisoformat(k): v for k, v in expected.items()}
    dt = START + timedelta(hours=9)
    expected[dt.isoformat()] = -.0005
    with pytest.raises(ForecastError):
        verify_price_readback(expected, observed, NOW)

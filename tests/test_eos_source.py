import copy
from datetime import UTC, datetime, timedelta

import pytest

from eos_pv_helper.eos_source import load_forecast
from eos_pv_helper.normalize import ForecastError, normalize


@pytest.fixture
def native_settings():
    return {"general": {"latitude": 52.52, "longitude": 13.405, "timezone": "Europe/Berlin"},
            "pvforecast": {"provider": "PVForecastImport", "forecastsolar": {},
                           "planes": [{"surface_tilt": 30, "surface_azimuth": 180,
                                       "peakpower": 11}]}}


def test_native_source_requires_two_opt_ins_and_no_fetch_by_default(tmp_path, native_settings):
    source = {"cache_file": str(tmp_path / "source.json"), "refresh_enabled": False}
    calls = []
    for flag in (False, True):
        with pytest.raises(ForecastError, match="approval"):
            load_forecast(source, native_settings, refresh=flag, fetcher=lambda *a: calls.append(a))
    assert not calls


def test_native_source_reuses_eos_settings_and_one_shared_cached_result(tmp_path, native_settings):
    source = {"cache_file": str(tmp_path / "source.json"), "refresh_enabled": True}
    calls = []
    now = datetime(2026, 6, 20, tzinfo=UTC)

    def fetcher(settings, folder):
        calls.append(settings)
        assert settings["pvforecast"]["planes"] == native_settings["pvforecast"]["planes"]
        assert settings["general"]["latitude"] == native_settings["general"]["latitude"]
        return {"timezone": "Europe/Berlin", "watts": {"2026-06-20 12:00:00": 1234}}

    raw, site, _, provenance = load_forecast(
        source, native_settings, refresh=True, now=now, fetcher=fetcher)
    assert raw[0]["power_w"] == 1234
    assert site["latitude"] == native_settings["general"]["latitude"]
    assert provenance["source_provider"] == "EOS.PVForecastForecastSolar"
    load_forecast(source, native_settings, refresh=False, now=now + timedelta(minutes=30),
                  fetcher=fetcher)
    assert len(calls) == 1
    with pytest.raises(ForecastError, match="approval"):
        load_forecast(source, native_settings, refresh=False,
                      now=now + timedelta(hours=2), fetcher=fetcher)
    changed = copy.deepcopy(native_settings)
    changed["pvforecast"]["planes"][0]["surface_tilt"] = 35
    with pytest.raises(ForecastError, match="approval"):
        load_forecast(source, changed, now=now, fetcher=fetcher)


def test_active_native_provider_prevents_second_fetcher(tmp_path, native_settings):
    native_settings["pvforecast"]["provider"] = "PVForecastForecastSolar"
    with pytest.raises(ForecastError, match="two active"):
        load_forecast({"cache_file": str(tmp_path / "source.json")}, native_settings)


def test_no_guessed_geometry(tmp_path, native_settings):
    del native_settings["pvforecast"]["planes"][0]["peakpower"]
    with pytest.raises(ForecastError, match="geometry"):
        load_forecast({"cache_file": str(tmp_path / "source.json")}, native_settings)


def test_explicit_hourly_support_points_keep_original_values_and_add_quarters():
    start = datetime(2026, 6, 20, 10, tzinfo=UTC)
    source = {start: 1000, start + timedelta(hours=1): 2000}
    result, report = normalize(source, start, 1, lambda *_: False, source_interval_seconds=3600)
    assert [r["pvforecast_ac_power"] for r in result["data"].values()] == [1000, 1250, 1500, 1750]
    assert report["interpolated_count"] == 3


def test_missing_hourly_day_support_point_is_not_interpolated():
    start = datetime(2026, 6, 20, 10, tzinfo=UTC)
    source = {start: 1000, start + timedelta(hours=2): 2000}
    with pytest.raises(ForecastError, match="daylight"):
        normalize(source, start, 2, lambda *_: False, source_interval_seconds=3600)

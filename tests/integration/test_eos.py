"""Real EOS import/optimization in a network-disabled disposable test container."""

import json

import pytest

pytest.importorskip("akkudoktoreos", reason="Run the isolated EOS integration image")


def test_real_eos_import_and_48_hour_optimization(config, forecast_case, tmp_path, monkeypatch):
    import asyncio

    import numpy as np
    from akkudoktoreos.core.coreabc import get_config, get_ems, get_prediction, singletons_init
    from akkudoktoreos.optimization.genetic.forecast import bounded_forecast_array
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from akkudoktoreos.optimization.genetic.geneticparams import GeneticOptimizationParameters
    from akkudoktoreos.utils.datetimeutil import to_datetime, to_duration

    from eos_pv_helper.app import run_once

    monkeypatch.setenv("EOS_DIR", str(tmp_path))
    monkeypatch.setenv("EOS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EOS_GENERAL__DATA_FOLDER_PATH", str(tmp_path / "data"))
    settings = get_config(init={
        "with_init_settings": True, "with_env_settings": True,
        "with_dotenv_settings": False, "with_file_settings": False,
        "with_file_secret_settings": False,
    })
    settings.merge_settings_from_dict({
        "general": {"latitude": 52.52, "longitude": 13.405, "timezone_override": "UTC"},
        "ems": {"mode": "DISABLED"},
        "pvforecast": {"provider": "PVForecastImport"},
        "prediction": {"hours": 48},
        "optimization": {"algorithm": "GENETIC", "genetic": {
            "horizon_hours": 48, "interval_sec": 900, "tail_horizon_hours": 0,
            "individuals": 12, "generations": 10, "workers": 1,
            "terminal_value_mode": "FIXED", "terminal_value_euro_per_kwh": 0,
        }},
    })
    singletons_init()
    start = to_datetime("2026-06-20T00:00:00Z", in_timezone="UTC")
    get_ems().set_start_datetime(start)
    payload, _ = run_once(config, source_reader=lambda _: [
        {"timestamp": dt.isoformat(), "power_w": value}
        for dt, value in forecast_case[2].items()
    ])

    async def import_and_read():
        prediction = get_prediction()
        provider = prediction.provider_by_id("PVForecastImport")
        await provider.import_from_json(json.dumps(payload))
        return await bounded_forecast_array(
            prediction, key="pvforecast_ac_power", start_datetime=start,
            end_datetime=start.add(hours=48), interval=to_duration(900),
        )

    power = asyncio.run(import_and_read())
    expected = [row["pvforecast_ac_power"] for row in payload["data"].values()]
    np.testing.assert_allclose(power, expected, rtol=0, atol=0)
    assert len(power) == 192 and np.isfinite(power).all()
    parameters = GeneticOptimizationParameters.model_validate({
        "ems": {
            "pv_forecast_wh": (power * 0.25).tolist(),
            "total_load": [125.0] * 192,
            "electricity_price_per_wh": [0.0003] * 192,
            "feed_in_tariff_per_wh": [0.00008] * 192,
            "price_per_wh_battery": 0,
        },
        "forecast_interval_seconds": 900,
        "pv_battery": {
            "device_id": "synthetic-battery", "capacity_wh": 10000,
            "initial_soc_percentage": 50, "min_soc_percentage": 0,
            "max_charge_power_w": 5000,
        },
        "inverter": {
            "device_id": "synthetic-inverter", "battery_id": "synthetic-battery",
            "max_power_wh": 11000,
        },
        "ev": None,
    })
    result = GeneticOptimization(fixed_seed=42).optimize_ems(
        parameters, ngen=1, individuals=12
    )
    assert result.interval_seconds == 900
    assert len(result.ac_charge) == 192
    assert np.isfinite(result.result.total_costs)


def test_reuse_native_eos_forecastsolar_without_any_real_http(tmp_path, monkeypatch):
    from akkudoktoreos.prediction import pvforecastforecastsolar as native

    from eos_pv_helper.eos_source import native_forecast

    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"info": {"timezone": "Europe/Berlin"}},
                    "result": {"watts": {"2026-06-20 12:00:00": 1234}}}

    def get(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(native.requests, "get", get)
    result = native_forecast({
        "general": {"latitude": 52.52, "longitude": 13.405,
                    "timezone_override": "Europe/Berlin"},
        "pvforecast": {"planes": [{"surface_tilt": 30, "surface_azimuth": 180,
                                    "peakpower": 11}], "forecastsolar": {}},
    }, tmp_path)
    assert result["watts"]["2026-06-20 12:00:00"] == 1234
    assert len(calls) == 1
    assert calls[0].endswith("/52.52/13.405/30.0/0.0/11.0")


def test_real_soc_retail_import_with_fees_and_optimize_endpoint(tmp_path, monkeypatch):
    """Actual EOS HTTP contracts, gross-fee preservation and a fresh GENETIC result."""
    from datetime import UTC, datetime, timedelta

    from akkudoktoreos.core.coreabc import get_config, get_ems, get_prediction, singletons_init
    from akkudoktoreos.prediction.elecfeefixed import ElecFeeFixed
    from akkudoktoreos.prediction.elecpriceimport import ElecPriceImport
    from akkudoktoreos.server import eos
    from fastapi.testclient import TestClient

    from eos_pv_helper.inputs import PRICE_KEY, SOC_KEY, retail_prices, soc_sample

    monkeypatch.setenv("EOS_DIR", str(tmp_path))
    monkeypatch.setenv("EOS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EOS_GENERAL__DATA_FOLDER_PATH", str(tmp_path / "data"))
    settings = get_config(init={"with_init_settings": True, "with_env_settings": True,
                               "with_dotenv_settings": False, "with_file_settings": False,
                               "with_file_secret_settings": False})
    settings.merge_settings_from_dict({
        "general": {"latitude": 52.52, "longitude": 13.405, "timezone_override": "UTC"},
        "ems": {"mode": "PREDICTION", "interval": 3600, "notify_url": None},
        "adapter": {"provider": None},
        "pvforecast": {"provider": "PVForecastImport"},
        "load": {"provider": "LoadImport"},
        "feedintariff": {"provider": "FeedInTariffImport"},
        "elecprice": {"provider": "ElecPriceImport", "elecpriceimport": {
            "import_file_path": None, "import_json": None}},
        "elecfee": {"provider": "ElecFeeFixed", "elecfeefixed": {
            "consumption_amt_kwh": {"windows": [
                {"start_time": "00:00", "duration": "24 hours", "value": .1138655}]},
            "consumption_percent_amt": {"windows": [
                {"start_time": "00:00", "duration": "24 hours", "value": 19}]} }},
        "prediction": {"hours": 48},
        "optimization": {"algorithm": "GENETIC", "genetic": {
            "horizon_hours": 24, "interval_sec": 3600, "tail_horizon_hours": 48,
            "individuals": 10, "generations": 10, "workers": 1, "seed": 42,
            "terminal_value_mode": "FIXED", "terminal_value_euro_per_kwh": 0}},
        "devices": {"max_batteries": 1, "max_electric_vehicles": 0, "max_inverters": 1,
                    "batteries": {"e3dc_s10e_pro": {"capacity_wh": 10000,
                         "max_charge_power_w": 5000}}, "electric_vehicles": {},
                    "inverters": {"test": {"battery_id": "e3dc_s10e_pro", "max_power_w": 11000}},
                    "home_appliances": {}},
    })
    singletons_init()
    now = datetime.now(UTC).replace(microsecond=0)
    start = now.replace(hour=0, minute=0, second=0)
    get_ems().set_start_datetime()
    client = TestClient(eos.app)
    prices = retail_prices({"currency": "EUR", "forecast": {"grid": [
        [int(start.timestamp()) + i*900, int(start.timestamp()) + (i+1)*900,
         -.10 if i % 8 == 0 else .30] for i in range(288)]}})
    response = client.put("/v1/prediction/import/ElecPriceImport", json=prices)
    assert response.status_code == 200, response.text
    for provider, key, value in [("PVForecastImport", "pvforecast_ac_power", 1000),
                                 ("LoadImport", "loadforecast_power_w", 500),
                                 ("FeedInTariffImport", "feed_in_tariff_wh", .00008)]:
        payload = {"tz": "UTC", "data": {(start + timedelta(minutes=i*15)).isoformat():
                                        {key: value} for i in range(288)}}
        response = client.put("/v1/prediction/import/" + provider, json=payload)
        assert response.status_code == 200, response.text
    sample = soc_sample({"entity_id": "sensor.evcc_battery_soc", "state": "55.5",
                         "last_updated": now.isoformat()}, now)
    response = client.put("/v1/measurement/value", params={"datetime": sample["source_timestamp"],
                          "key": SOC_KEY, "value": sample["factor"]})
    assert response.status_code == 200, response.text
    response = client.get("/v1/measurement/series", params={"key": SOC_KEY, "processing": "raw"})
    assert .555 in response.json()["data"].values()

    # Native EMS calls its prediction pipeline. Isolate it from all external services:
    # run the real import provider update only; it must not invoke fee calculation.
    calls = []

    async def forbidden_fees(*args, **kwargs):
        pytest.fail("Gross retail imports must never be recalculated with EOS fees")

    async def cached_updates(self, *args, **kwargs):
        calls.append(True)
        await ElecFeeFixed().update_data()
        await ElecPriceImport().update_data()

    monkeypatch.setattr(ElecPriceImport, "_apply_fees", forbidden_fees)
    monkeypatch.setattr(type(get_prediction()), "update_data", cached_updates)
    fees_before = settings.elecfee.model_dump()
    assert settings.elecfee.elecfeefixed.consumption_amt_kwh.windows[0].value == .1138655
    assert settings.elecfee.elecfeefixed.consumption_percent_amt.windows[0].value == 19
    result = client.post("/v1/optimize", json={"soc": {"e3dc_s10e_pro": 55}})
    assert result.status_code == 200, result.text
    solution = result.json()
    assert solution["interval_seconds"] == 3600
    assert len(solution["ac_charge"]) == 24
    assert isinstance(solution["result"]["total_costs"], (float, int))
    assert calls  # The event's native EOS update was exercised, not a helper scheduler.
    assert settings.ems.mode == "PREDICTION" and settings.ems.interval == 3600
    assert settings.elecfee.model_dump() == fees_before
    readback = client.get("/v1/prediction/series", params={"key": PRICE_KEY, "processing": "raw"})
    observed = readback.json()["data"]
    assert set(observed.values()) == {-.0001, .0003}

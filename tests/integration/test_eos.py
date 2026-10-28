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

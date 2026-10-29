"""Native EOS with partial PV, real readback filtering and a local evcc HTTP fixture."""

import asyncio
import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("akkudoktoreos", reason="Run the isolated EOS integration image")


def test_partial_pv_history_trim_verified_evcc_soc_and_native_optimization(tmp_path, monkeypatch):
    import numpy as np
    from akkudoktoreos.core.coreabc import get_config, get_ems, get_prediction, singletons_init
    from akkudoktoreos.optimization.genetic.configrequest import ConfigOptimizationRequest
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from akkudoktoreos.server import eos
    from akkudoktoreos.utils.datetimeutil import to_datetime
    from fastapi.testclient import TestClient

    from eos_pv_helper.app import request_json
    from eos_pv_helper.evcc_source import evcc_soc_sample
    from eos_pv_helper.inputs import (
        PRICE_KEY,
        SOC_KEY,
        coverage,
        native_price_runtime,
        raw_series,
        verify_price_readback,
    )
    from eos_pv_helper.normalize import STEP, ForecastError, SolarNight, normalize

    monkeypatch.setenv("EOS_DIR", str(tmp_path))
    monkeypatch.setenv("EOS_CONFIG_DIR", str(tmp_path))
    settings = get_config(init={"with_init_settings": True, "with_env_settings": True,
                               "with_dotenv_settings": False, "with_file_settings": False,
                               "with_file_secret_settings": False})
    settings.merge_settings_from_dict({
        "general": {"latitude": 52.52, "longitude": 13.405, "timezone_override": "UTC"},
        "ems": {"mode": "PREDICTION", "interval": 3600, "notify_url": None},
        "adapter": {"provider": None}, "weather": {"provider": None},
        "pvforecast": {"provider": "PVForecastImport"}, "load": {"provider": "LoadImport"},
        "feedintariff": {"provider": "FeedInTariffImport"},
        "elecprice": {"provider": "ElecPriceImport", "elecpriceimport": {
            "import_file_path": None, "import_json": None}},
        "prediction": {"hours": 48}, "optimization": {"algorithm": "GENETIC", "genetic": {
            "interval_sec": 3600, "horizon_hours": 24, "tail_horizon_hours": 48,
            "individuals": 10, "generations": 10, "workers": 1, "seed": 42,
            "terminal_value_mode": "FIXED", "terminal_value_euro_per_kwh": 0}},
        "devices": {"max_batteries": 1, "max_inverters": 1, "max_electric_vehicles": 0,
                    "batteries": {"e3dc_s10e_pro": {"capacity_wh": 10000,
                                                  "max_charge_power_w": 5000}},
                    "inverters": {"test": {"battery_id": "e3dc_s10e_pro", "max_power_w": 11000}},
                    "electric_vehicles": {}, "home_appliances": {}},
    })
    singletons_init()
    start = datetime(2026, 6, 20, tzinfo=UTC)
    now = start + timedelta(hours=12)
    get_ems().set_start_datetime(to_datetime(now))
    monkeypatch.setattr(type(get_ems()), "_genetic_solution", None)
    client = TestClient(eos.app)
    night = SolarNight(52.52, 13.405, "Europe/Berlin")
    values = {start + i * STEP: 1234.567 for i in range(148)
              if not night(start + i * STEP, start + (i + 1) * STEP)}
    pv, pv_report = normalize(values, start, 48, night, minimum_hours=24)
    assert pv_report["validated_hours"] == 37
    response = client.put("/v1/prediction/import/PVForecastImport", json=pv)
    assert response.status_code == 200, response.text
    price_values = {(start + i * STEP).isoformat(): -.0001 if i % 8 == 0 else .0003 for i in range(192)}
    prices = {"tz": "UTC", "data": {key: {PRICE_KEY: value} for key, value in price_values.items()}}
    assert client.put("/v1/prediction/import/ElecPriceImport", json=prices).status_code == 200
    default = raw_series(client.get("/v1/prediction/series", params={
        "key": PRICE_KEY, "processing": "raw", "dropna": False}).json())
    verified = verify_price_readback(price_values, default, now)
    assert len(verified["historical_missing_intervals"]) == 48  # GET's EMS lower bound, not lost data.
    assert verified["future_missing_intervals"] == []
    full = raw_series(client.get("/v1/prediction/series", params={
        "key": PRICE_KEY, "processing": "raw", "dropna": False,
        "start_datetime": start.isoformat(), "end_datetime": (start + timedelta(hours=48)).isoformat()}).json())
    assert len(full) == 192
    default.pop(now + timedelta(hours=1))
    with pytest.raises(ForecastError):
        verify_price_readback(price_values, default, now)

    status_error, calls = [""], []

    class Evcc(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls.append(self.path)
            if self.path == "/api/state":
                result = {"version": "0.318.1", "battery": {"devices": [
                    {"name": "db:7", "soc": 13, "power": 354}]}}
            elif self.path.endswith("/status"):
                assert self.headers["Cache-Control"] == "no-cache, no-store"
                result = {"soc": {"value": 13, "error": status_error[0]},
                          "power": {"value": 400, "error": ""}}
            else:
                result = {"name": "db:7", "type": "template", "config": {
                    "template": "e3dc-rscp", "usage": "battery"}}
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Evcc)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        snapshot = request_json(origin + "/api/state")
        soc_config = {"device_name": "db:7", "freshness": "e3dc-rscp-status"}
        sample = evcc_soc_sample(snapshot, soc_config, origin, request_json, lambda: now)
        assert sample["factor"] == .13 and sample["freshness_verified"]
        response = client.put("/v1/measurement/value", params={
            "datetime": sample["source_timestamp"], "key": SOC_KEY, "value": sample["factor"]})
        assert response.status_code == 200, response.text
        status_error[0] = "device offline"
        with pytest.raises(ForecastError):
            evcc_soc_sample(snapshot, soc_config, origin, request_json, lambda: now + timedelta(seconds=301))
        measured = client.get("/v1/measurement/series", params={"key": SOC_KEY, "processing": "raw"}).json()
        assert .13 in measured["data"].values()
        assert calls.count("/api/state") == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)

    for provider, key, value in [("LoadImport", "loadforecast_power_w", 500),
                                 ("FeedInTariffImport", "feed_in_tariff_wh", .00008)]:
        data = {"tz": "UTC", "data": {(start + i * STEP).isoformat(): {key: value} for i in range(288)}}
        assert client.put("/v1/prediction/import/" + provider, json=data).status_code == 200
    series = {key: raw_series(client.get("/v1/prediction/series", params={
        "key": key, "processing": "raw", "dropna": False}).json()) for key in
        ("pvforecast_ac_power", "loadforecast_power_w", PRICE_KEY, "feed_in_tariff_wh")}
    plan = coverage(settings.model_dump(), series, now,
                    end_limits={"pvforecast_ac_power": start + timedelta(hours=37)})
    assert plan["control_hours"] == 24 and plan["effective_tail_hours"] == 1

    async def no_external_update(self, *args, **kwargs):
        pass

    monkeypatch.setattr(type(get_prediction()), "update_data", no_external_update)
    runtime_prices = native_price_runtime(settings.model_dump(), full, plan, now)
    parameters = asyncio.run(ConfigOptimizationRequest(
        forecasts={"electricity_price_per_wh": runtime_prices}).resolve())
    assert len(parameters.ems.pv_forecast_wh) == 37  # Stored old PV tail is excluded at runtime.
    assert parameters.pv_battery.initial_soc_percentage == 13
    result = GeneticOptimization(fixed_seed=42).optimize_ems(parameters=parameters, ngen=1, individuals=10)
    assert len(result.ac_charge) == 24 and np.isfinite(result.result.total_costs)
    assert settings.ems.mode == "PREDICTION"

"""Closed synthetic sync transport with one native FIXED-CONTROL model response.

Review tooling only. No HTTP client, optimization search, production configuration,
private inputs or device access. The actual sync/evidence implementation is imported
from the installed helper, so the same tool can test a packaged candidate image.
"""

import argparse
import copy
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from eos_pv_helper import economics, economics_native, historical
from eos_pv_helper.storage import atomic_json
from eos_pv_helper.sync import TESTED_EOS_VERSION, sync_once


def deny_real_actions():
    """Fail any accidental HTTP/socket/process/search in this TEST harness."""
    from eos_pv_helper.replay_worker_job import deny_external_actions

    def audit(event, args):
        # URL validation of literal loopback addresses needs no DNS/socket.
        if event == "socket.getaddrinfo" and args[0] == "127.0.0.1":
            return
        deny_external_actions(event, args)

    sys.addaudithook(audit)
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization

    def forbidden(*args, **kwargs):
        raise RuntimeError("synthetic_review_optimizer_search_forbidden")

    GeneticOptimization.optimize_ems = forbidden


class SyntheticEvent:
    def __init__(self, root, template, *, now=None):
        self.root, self.template = Path(root), Path(template)
        self.now = now or datetime(2026, 10, 29, 13, 5, tzinfo=UTC)
        self.calls, self.model_calls = [], 0
        self.root.mkdir(mode=0o700, exist_ok=True)
        self.config = {"timezone": "Europe/Berlin", "output": {"directory": str(self.root)},
            "eos": {"url": "http://127.0.0.1:8503", "write_enabled": True},
            "evcc": {"url": "http://127.0.0.1:7070"},
            "soc": {"enabled": True, "source": "evcc", "device_name": "db:7",
                    "freshness": "e3dc-rscp-status", "write_enabled": True},
            "prices": {"enabled": True, "write_enabled": True, "retail_prices_confirmed": True},
            "trigger": {"enabled": True, "run_enabled": True}, "evidence": {"enabled": True}}
        self.settings = {"general": {"timezone": "Europe/Berlin"},
            "ems": {"mode": "PREDICTION", "interval": 3600}, "adapter": {"provider": None},
            "devices": {"batteries": {historical.SOC_DEVICE: {
                "measurement_key_soc_factor": historical.SOC_DEVICE+"-soc-factor"}}},
            "prediction": {"hours": 48}, "optimization": {"algorithm": "GENETIC",
                "genetic": {"interval_sec": 3600, "horizon_hours": 24, "tail_horizon_hours": 24}},
            "elecprice": {"provider": "ElecPriceImport"},
            "pvforecast": {"provider": "PVForecastImport"},
            "elecfee": {"provider": "ElecFeeFixed"}}
        self.origin = self.now.astimezone(ZoneInfo("Europe/Berlin")).replace(
            hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        stamps = [self.origin+timedelta(minutes=15*i) for i in range(288)]
        self.grid = [[int(dt.timestamp()), int((dt+timedelta(minutes=15)).timestamp()), .3]
                     for dt in stamps]
        self.series = {key: {dt.isoformat(): value for dt in stamps}
                       for key, value in (("pvforecast_ac_power", 1000),
                                          ("loadforecast_power_w", 500), ("feed_in_tariff_wh", .00008))}

    def pv(self, config, **kwargs):
        series = self.series["pvforecast_ac_power"]
        value = {"data": {key: {"pvforecast_ac_power": v} for key, v in series.items()}}
        report = {"count": len(series), "checked_at_utc": self.now.isoformat(),
            "source_fetched_at_utc": self.now.isoformat(), "source_max_age_seconds": 3600,
            "start_utc": min(series), "end_exclusive_utc": (
                datetime.fromisoformat(max(series))+timedelta(minutes=15)).isoformat(),
            "import_verified": kwargs.get("write_eos", False)}
        atomic_json(self.root / "forecast.json", value)
        atomic_json(self.root / "report.json", report)
        return value, report

    def response(self, request):
        """One real forward model, explicit controls and parameters; no solver decisions."""
        solution = json.loads(self.template.read_bytes())
        start = self.now.replace(minute=0, second=0, microsecond=0)
        solution["start_solution_datetime"] = start.isoformat()
        params = solution["parameters"]
        params["pv_battery"].update(device_id=historical.SOC_DEVICE,
            initial_soc_percentage=request["soc"][historical.SOC_DEVICE])
        params["inverter"]["battery_id"] = historical.SOC_DEVICE
        request_origin = self.now.astimezone(ZoneInfo("Europe/Berlin")).replace(
            hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        first = int((start-request_origin).total_seconds()/3600)
        prices = request["forecasts"]["electricity_price_per_wh"][first:]
        for source, target in (("pvforecast_ac_power", "pv_forecast_wh"),
                                ("loadforecast_power_w", "total_load"),
                                ("feed_in_tariff_wh", "feed_in_tariff_per_wh")):
            series = {datetime.fromisoformat(k): v for k, v in self.series[source].items()}
            params["ems"][target] = historical.interval_averages(series, start, len(prices), 3600)
        params["ems"]["electricity_price_per_wh"] = prices
        # The public fixture supplies the result shape required by project(); its
        # numerical results are completely replaced by THIS actual native model call.
        solution["result"]["electricity_price"] = prices[:24]
        solution["result"]["feed_in_tariff"] = params["ems"]["feed_in_tariff_per_wh"][:24]
        run = economics_native.simulate(economics.project(solution), baseline=False, load_scale=1)
        self.model_calls += 1
        solution["result"] = run["result"]
        solution["terminal_value"].update(battery_energy_wh=run["end_usable_ac_wh"],
            credited_euro=economics.terminal_value(solution["terminal_value"]["curve"], run["end_usable_ac_wh"]))
        return solution

    def http(self, url, **kwargs):
        """An in-memory protocol stub; an unexpected endpoint never reaches a socket."""
        method, parts = kwargs.get("method", "GET"), urlsplit(url)
        path, query = parts.path, parse_qs(parts.query)
        self.calls.append((method, path, copy.deepcopy(kwargs)))
        assert parts.hostname == "127.0.0.1" and parts.port in (8503, 7070)
        if method == "GET" and path == "/v1/config":
            return copy.deepcopy(self.settings)
        if method == "GET" and path == "/openapi.json":
            return {"info": {"version": TESTED_EOS_VERSION}, "components": {"schemas": {
                "PydanticDateTimeDataFrame": {"required": ["data"], "properties": {"tz": {}}}}},
                "paths": {
                "/v1/prediction/import/{provider_id}": {"put": {"requestBody": {"content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/PydanticDateTimeDataFrame"}}}}}},
                "/v1/measurement/value": {"put": {"parameters": [
                    {"in": "query", "name": key} for key in ("datetime", "key", "value")]}},
                "/v1/optimize": {"post": {"requestBody": {"content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/ConfigOptimizationRequest"}}}}}}}}
        if method == "GET" and path == "/api/state":
            return {"version": "0.318.1", "currency": "EUR", "error": None,
                "battery": {"devices": [{"name": "db:7", "soc": 40, "power": 0}]},
                "forecast": {"grid": copy.deepcopy(self.grid)}}
        if method == "GET" and path == "/api/config/devices/meter/7":
            return {"name": "db:7", "type": "template", "config": {
                "template": "e3dc-rscp", "usage": "battery"}}
        if method == "GET" and path == "/api/config/devices/meter/db:7/status":
            return {"soc": {"value": 40, "error": ""}, "power": {"value": 0, "error": ""}}
        if method == "PUT" and path == "/v1/measurement/value":
            self.series[query["key"][0]] = {query["datetime"][0]: float(query["value"][0])}
            return None
        if method == "PUT" and path == "/v1/prediction/import/ElecPriceImport":
            self.series[historical.PRICE_KEY] = {k: v[historical.PRICE_KEY]
                                               for k, v in kwargs["payload"]["data"].items()}
            return None
        if method == "GET" and path in ("/v1/prediction/series", "/v1/measurement/series"):
            assert query["processing"] == ["raw"] and query["dropna"] == ["false"]
            return {"data": self.series[query["key"][0]]}
        if method == "POST" and path == "/v1/optimize":
            return self.response(kwargs["payload"])
        raise AssertionError("Unexpected synthetic transport operation")

    def tick(self):
        return sync_once(self.config, write_eos=True, now=self.now, clock=lambda: self.now,
                         http=self.http, pv_runner=self.pv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    args = parser.parse_args()
    # Only a NEW explicitly synthetic directory can be used by this CLI.
    args.destination.mkdir(mode=0o700)
    os.environ["DRY_RUN"] = "false"  # In this offline test process only; transport is closed above.
    deny_real_actions()
    event = SyntheticEvent(args.destination, args.template)
    report = event.tick()
    assert report["errors"] == {} and report["evidence"]["status"] == "archived", report["evidence"]
    assert event.tick()["evidence"]["status"] == "archived" and event.model_calls == 1
    print(json.dumps({"synthetic_only": True, "real_native_fixed_control_calls": 1,
                      "optimizer_searches": 0, "archives": 1, "restart_did_not_dispatch": True}))


if __name__ == "__main__":
    main()

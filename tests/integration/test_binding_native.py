"""Actual pinned EOS normalization only: NO optimizer search, HTTP or dispatch."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from synthetic_binding import averages, parameters  # noqa: E402
from test_binding_contract import synthetic  # noqa: E402

from eos_pv_helper import historical  # noqa: E402


@pytest.mark.parametrize("now", [datetime(2026, 3, 29, 1, 5, tzinfo=UTC),
    datetime(2026, 10, 25, 0, 5, tzinfo=UTC), datetime(2026, 10, 25, 1, 5, tzinfo=UTC)])
def test_real_native_midnight_trimming_matches_bound_response_without_search(now, monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from akkudoktoreos.optimization.genetic.geneticparams import GeneticOptimizationParameters
    from akkudoktoreos.utils.datetimeutil import to_datetime
    from requests.sessions import Session

    def forbidden(*args, **kwargs):
        pytest.fail("No optimizer or HTTP in native input-normalization test")
    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)
    manifest, files = synthetic(now)
    values = {n: json.loads(raw) for n, raw in files.items()}
    receipt = values["sync-report.json"]["event"]["request_binding"]
    prices = receipt["request"]["forecasts"]["electricity_price_per_wh"]
    origin = historical.timestamp(receipt["origin_utc"])
    supplied = parameters(prices,
        averages(values["forecast.json"]["data"], "pvforecast_ac_power", origin, len(prices)), 55)
    supplied["ev"] = None
    supplied["ems"]["price_per_wh_battery"] = 0
    native_inputs = GeneticOptimizationParameters.model_validate(supplied)
    start = values["sync-report.json"]["event"]["start_utc"]
    proxy = SimpleNamespace(ems=SimpleNamespace(start_datetime=to_datetime(start, in_timezone="Europe/Berlin")),
        slot_duration_h=1, _genetic_cfg=SimpleNamespace(interval_sec=3600), slots_per_hour=1,
        prediction_slots=48, _prediction_hours_cfg=48)
    proxy._start_day_slot = lambda: GeneticOptimization._start_day_slot(proxy)
    normalized = GeneticOptimization._parameters_for_slot_grid(proxy, native_inputs)
    solution = values["solution-"+manifest["event_version"]+".json"]
    assert normalized.ems.pv_forecast_wh == solution["parameters"]["ems"]["pv_forecast_wh"]
    assert normalized.ems.electricity_price_per_wh == solution["parameters"]["ems"]["electricity_price_per_wh"]
    assert len(normalized.ems.total_load) == 34
    assert historical.validate(manifest, files, now=now+timedelta(days=1))["input_binding_complete"]

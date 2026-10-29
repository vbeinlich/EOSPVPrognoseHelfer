import copy
from datetime import UTC, datetime, timedelta

import pytest

from eos_pv_helper.evcc_source import evcc_soc_sample
from eos_pv_helper.normalize import ForecastError

NOW = datetime(2026, 10, 29, 12, tzinfo=UTC)


@pytest.fixture
def case():
    return {"config": {"device_name": "db:7", "freshness": "e3dc-rscp-status"},
            "state": {"version": "0.318.1", "error": None, "historyUpdated": NOW.isoformat(),
                      "battery": {"soc": 99, "devices": [{"name": "db:7", "soc": 13, "power": 354},
                                                         {"name": "db:8", "soc": 87, "power": 250}]}},
            "meter": {"name": "db:7", "type": "template", "config": {
                "template": "e3dc-rscp", "usage": "battery"}},
            "status": {"soc": {"value": 13, "error": ""}, "power": {"value": 400, "error": ""}},
            "calls": []}


def sample(case, clock=lambda: NOW):
    def http(url, **kwargs):
        assert kwargs.get("method", "GET") == "GET"
        case["calls"].append(url)
        return case["status"] if url.endswith("/status") else case["meter"]
    return evcc_soc_sample(case["state"], case["config"], "http://127.0.0.1:7070", http, clock)


def test_unchanged_soc_has_new_successful_uncached_read_proof_not_http_state_time(case):
    first = sample(case)
    second = sample(case, clock=lambda: NOW + timedelta(minutes=1))
    assert first["percent"] == second["percent"] == 13  # Never use the aggregate 99%.
    assert first["factor"] == .13 and first["freshness_verified"] is True
    assert second["source_timestamp"] != first["source_timestamp"]
    assert first["device_timestamp_available"] is False
    assert first["timestamp_kind"] == "successful_uncached_device_read_lower_bound"


@pytest.mark.parametrize("failure", ["no-proof", "wrong-version", "wrong-device", "duplicate",
                                     "null-soc", "bad-soc", "bad-power", "error", "cached-driver",
                                     "wrong-template", "wrong-config-name", "getter-failed",
                                     "missing-getter", "changed-soc", "asleep"])
def test_unproven_or_invalid_battery_is_rejected_without_fallback(case, failure):
    state, config = case["state"], case["config"]
    if failure == "no-proof":
        config["freshness"] = "state"
    elif failure == "wrong-version":
        state["version"] = "untested"
    elif failure == "wrong-device":
        config["device_name"] = "db:99"
    elif failure == "duplicate":
        state["battery"]["devices"].append(copy.deepcopy(state["battery"]["devices"][0]))
    elif failure == "null-soc":
        state["battery"]["devices"][0]["soc"] = None
    elif failure == "bad-soc":
        state["battery"]["devices"][0]["soc"] = 101
    elif failure == "bad-power":
        state["battery"]["devices"][0]["power"] = 1e9
    elif failure == "error":
        state["error"] = "meter error"
    elif failure == "cached-driver":
        case["meter"]["config"]["cache"] = "1h"
    elif failure == "wrong-template":
        case["meter"]["config"]["template"] = "e3dc"
    elif failure == "wrong-config-name":
        case["meter"]["name"] = "db:8"
    elif failure == "getter-failed":
        case["status"]["soc"]["error"] = "timeout"
    elif failure == "missing-getter":
        case["status"].pop("soc")
    elif failure == "changed-soc":
        case["status"]["soc"]["value"] = 12
    else:
        case["status"]["soc"]["asleep"] = True
    with pytest.raises(ForecastError) as error:
        sample(case)
    assert error.value.report["freshness_verified"] is False
    assert error.value.report["source_timestamp"] is None


def test_slow_device_poll_and_expired_proof_fail_closed(case):
    for elapsed in (16, 301):
        times = iter([NOW, NOW + timedelta(seconds=elapsed)])
        with pytest.raises(ForecastError):
            sample(case, clock=lambda: next(times))


def test_restarting_with_cached_state_cannot_reuse_old_proof(case):
    assert sample(case)["freshness_verified"]
    case["status"]["soc"]["error"] = "poller stopped"
    with pytest.raises(ForecastError):
        sample(case, clock=lambda: NOW + timedelta(seconds=301))

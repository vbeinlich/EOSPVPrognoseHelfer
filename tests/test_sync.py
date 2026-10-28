import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from eos_pv_helper.inputs import PRICE_KEY, SOC_KEY
from eos_pv_helper.normalize import ForecastError
from eos_pv_helper.sync import simulation_safe, sync_once, verify_sync_contract


@pytest.fixture
def sync_case(config, monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    now = datetime.now(UTC).replace(microsecond=0)
    # Start before the current hour; cover complete tomorrow and the control horizon.
    start = now.replace(hour=0, minute=0, second=0) - timedelta(hours=3)
    config.update({"soc": {"enabled": True, "url": "http://127.0.0.1:8123",
                           "write_enabled": True, "bearer_token_env": "HA_TOKEN"},
                   "prices": {"enabled": True, "url": "http://127.0.0.1:7070",
                              "write_enabled": True, "retail_prices_confirmed": True},
                   "trigger": {"enabled": True, "run_enabled": True}})
    config["eos"].update(url="http://127.0.0.1:8503", write_enabled=True)
    schema = json.loads((Path(__file__).parent / "fixtures/eos-sync-contract.json").read_text())
    settings = {"general": {"timezone": "Europe/Berlin"},
                "ems": {"mode": "PREDICTION", "interval": 3600, "notify_url": None},
                "adapter": {"provider": None}, "devices": {
                    "batteries": {"e3dc_s10e_pro": {"measurement_key_soc_factor": SOC_KEY}}},
                "prediction": {"hours": 48}, "optimization": {"algorithm": "GENETIC",
                    "genetic": {"interval_sec": 3600, "horizon_hours": 24,
                                "tail_horizon_hours": 48, "measurement_max_age_seconds": 300}},
                "elecprice": {"provider": "ElecPriceImport"},
                "pvforecast": {"provider": "PVForecastImport"},
                "elecfee": {"provider": "ElecFeeFixed", "consumption_amt": .1138655}}
    shared = {"settings": settings, "schema": schema, "calls": [], "series": {},
              "ha": {"entity_id": "sensor.evcc_battery_soc", "state": "55.5",
                     "last_updated": now.isoformat()},
              "evcc": {"currency": "EUR", "forecast": {"grid": [
                  [int(start.timestamp()) + i * 900, int(start.timestamp()) + (i+1)*900, .30]
                  for i in range(288)]}}}
    for key, value in [("pvforecast_ac_power", 1000), ("loadforecast_power_w", 500),
                       ("feed_in_tariff_wh", .00008)]:
        shared["series"][key] = {(start + timedelta(minutes=15*i)).isoformat(): value
                                 for i in range(288)}

    def http(url, **kwargs):
        method = kwargs.get("method", "GET")
        shared["calls"].append((method, url, kwargs))
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if parts.path == "/v1/config":
            return copy.deepcopy(shared["settings"])
        if parts.path == "/openapi.json":
            return shared["schema"]
        if parts.path == "/api/states/sensor.evcc_battery_soc":
            return shared["ha"]
        if parts.path == "/api/state":
            return shared["evcc"]
        if parts.path == "/v1/measurement/value":
            assert method == "PUT"
            shared["series"][SOC_KEY] = {query["datetime"][0]: float(query["value"][0])}
            return None
        if parts.path == "/v1/prediction/import/ElecPriceImport":
            assert method == "PUT"
            shared["series"][PRICE_KEY] = {k: v[PRICE_KEY] for k, v in kwargs["payload"]["data"].items()}
            return None
        if parts.path in ("/v1/prediction/series", "/v1/measurement/series"):
            assert query["processing"] == ["raw"]
            return {"data": shared["series"].get(query["key"][0], {})}
        if parts.path == "/v1/optimize":
            assert method == "POST" and kwargs["payload"] == {"soc": {"e3dc_s10e_pro": 55}}
            if shared.get("timeout"):
                raise TimeoutError("ambiguous")
            result_start = now.replace(minute=0, second=0)
            return {"interval_seconds": 3600, "start_solution_datetime": result_start.isoformat(),
                    "ac_charge": [0.] * 24, "dc_charge": [1.] * 24,
                    "discharge_allowed": [1.] * 24, "result": {"total_costs": 1.25}}
        pytest.fail("Unexpected endpoint: " + url)

    def pv_runner(*args, **kwargs):
        if shared.get("pv_fail"):
            raise ForecastError("Synthetic daylight gap")
        shared["pv_calls"] = shared.get("pv_calls", 0) + 1
        return {}, {"import_verified": kwargs.get("write_eos", False)}

    shared.update(now=now, http=http, pv_runner=pv_runner, config=config)
    return shared


def tick(case, **kwargs):
    kwargs.setdefault("clock", lambda: case["now"])
    return sync_once(case["config"], now=case["now"], http=case["http"],
                     pv_runner=case["pv_runner"], **kwargs)


def writes(case, method=None):
    return [call for call in case["calls"] if call[0] != "GET" and (not method or call[0] == method)]


def test_default_dry_run_even_with_flag_and_all_config_opt_ins(sync_case):
    report = tick(sync_case, write_eos=True)
    assert report["errors"] == {}
    assert report["event"]["status"] == "ready-dry-run"
    assert writes(sync_case) == []
    assert report["soc"]["factor"] == .555
    assert json.loads((Path(sync_case["config"]["output"]["directory"]) / "prices.json").read_text())


def test_imports_verified_once_per_version_across_restart(sync_case, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    assert tick(sync_case, write_eos=True)["event"]["status"] == "succeeded"
    assert len(writes(sync_case, "POST")) == 1
    report = tick(sync_case, write_eos=True)
    assert report["event"]["status"] == "succeeded"
    assert len(writes(sync_case, "POST")) == 1
    assert sync_case["pv_calls"] == 1
    assert all(urlsplit(url).path in {"/v1/measurement/value",
               "/v1/prediction/import/ElecPriceImport", "/v1/optimize"} for _, url, _ in writes(sync_case))
    query = parse_qs(urlsplit(writes(sync_case)[0][1]).query)
    assert query["datetime"] == [sync_case["ha"]["last_updated"]]
    assert query["value"] == ["0.555"]


def test_timeout_claim_prevents_retry_after_restart(sync_case, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    sync_case["timeout"] = True
    report = tick(sync_case, write_eos=True)
    assert "event" in report["errors"]
    assert report["event"]["status"] == "uncertain"
    assert tick(sync_case, write_eos=True)["event"]["status"] == "uncertain"
    assert len(writes(sync_case, "POST")) == 1


def test_dry_run_does_not_consume_live_version(sync_case, monkeypatch):
    assert tick(sync_case)["event"]["status"] == "ready-dry-run"
    monkeypatch.setenv("DRY_RUN", "false")
    assert tick(sync_case, write_eos=True)["event"]["status"] == "succeeded"
    assert sync_case["pv_calls"] == 2  # Dry-run validation cannot substitute a real PV import.


@pytest.mark.parametrize("component", ["soc", "prices", "trigger"])
def test_individual_write_approvals_are_required(sync_case, monkeypatch, component):
    monkeypatch.setenv("DRY_RUN", "false")
    sync_case["config"][component]["run_enabled" if component == "trigger" else "write_enabled"] = False
    report = tick(sync_case, write_eos=True)
    assert not writes(sync_case, "POST")
    if component != "trigger":
        assert "event" in report["errors"]


def test_stale_soc_blocks_only_soc_and_event_not_price_cache(sync_case, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    sync_case["ha"]["last_updated"] = (sync_case["now"] - timedelta(seconds=301)).isoformat()
    report = tick(sync_case, write_eos=True)
    assert "soc" in report["errors"] and "event" in report["errors"]
    assert not writes(sync_case, "POST")
    assert any("ElecPriceImport" in url for _, url, _ in writes(sync_case))
    # A temporarily invalid input must not consume the event.
    sync_case["ha"]["last_updated"] = sync_case["now"].isoformat()
    assert tick(sync_case, write_eos=True)["event"]["status"] == "succeeded"


def test_pv_error_does_not_suppress_soc_or_prices(sync_case):
    sync_case["pv_fail"] = True
    report = tick(sync_case)
    assert "pv" in report["errors"]
    assert report["soc"]["percent"] == 55.5
    assert report["prices"]["count"] == 288
    assert not writes(sync_case)


def test_energycharts_blocks_price_write_without_changing_config(sync_case, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    sync_case["settings"]["elecprice"]["provider"] = "ElecPriceEnergyCharts"
    report = tick(sync_case, write_eos=True)
    assert "prices" in report["errors"]
    assert all(urlsplit(url).path == "/v1/measurement/value" for _, url, _ in writes(sync_case))


@pytest.mark.parametrize("kind", ["adapter", "webhook", "mode", "ev", "other-battery"])
def test_no_simulation_with_device_paths_or_unvalidated_soc(sync_case, kind):
    settings = sync_case["settings"]
    if kind == "adapter":
        settings["adapter"]["provider"] = ["HomeAssistant"]
    elif kind == "webhook":
        settings["ems"]["notify_url"] = "http://127.0.0.1/callback"
    elif kind == "mode":
        settings["ems"]["mode"] = "OPTIMIZATION"
    elif kind == "ev":
        settings["devices"]["electric_vehicles"] = {"ev": {}}
    else:
        settings["devices"]["batteries"] = {"other": {}}
    with pytest.raises(ForecastError):
        simulation_safe(settings)


def test_live_contract_and_changed_version(sync_case):
    schema = sync_case["schema"]
    verify_sync_contract(schema)
    schema["info"]["version"] = "untested"
    with pytest.raises(ForecastError, match="version"):
        verify_sync_contract(schema)


def test_failed_readback_prevents_optimization(sync_case, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    original = sync_case["http"]

    def broken(url, **kwargs):
        result = original(url, **kwargs)
        if "/v1/measurement/series" in url:
            return {"data": {sync_case["now"].isoformat(): .99}}
        return result

    sync_case["http"] = broken
    assert "soc" in tick(sync_case, write_eos=True)["errors"]
    assert not writes(sync_case, "POST")


def test_new_price_revision_dispatches_but_soc_update_does_not(sync_case, monkeypatch):
    from zoneinfo import ZoneInfo

    monkeypatch.setenv("DRY_RUN", "false")
    first = tick(sync_case, write_eos=True)
    sync_case["ha"]["state"] = "65"
    assert tick(sync_case, write_eos=True)["event"]["version"] == first["event"]["version"]
    assert len(writes(sync_case, "POST")) == 1
    tomorrow = (sync_case["now"].astimezone(ZoneInfo("Europe/Berlin")).date()
                + timedelta(days=1))
    for row in sync_case["evcc"]["forecast"]["grid"]:
        if datetime.fromtimestamp(row[0], UTC).astimezone(ZoneInfo("Europe/Berlin")).date() == tomorrow:
            row[2] = -.1
            break
    # The HTTP test double expects the original SoC in an actual POST.
    sync_case["ha"]["state"] = "55.5"
    second = tick(sync_case, write_eos=True)
    assert second["event"]["status"] == "succeeded"
    assert second["event"]["version"] != first["event"]["version"]
    assert len(writes(sync_case, "POST")) == 2


def test_no_duplicate_post_if_claim_cannot_be_persisted(sync_case, monkeypatch):
    from eos_pv_helper import sync

    monkeypatch.setenv("DRY_RUN", "false")
    original = sync.atomic_json

    def no_claim(path, data):
        if Path(path).name == "sync-state.json" and data.get("events"):
            raise OSError("Disk full")
        original(path, data)

    monkeypatch.setattr(sync, "atomic_json", no_claim)
    with pytest.raises(OSError):
        tick(sync_case, write_eos=True)
    assert not writes(sync_case, "POST")


def test_missing_price_publication_is_waiting_not_failed(sync_case):
    sync_case["evcc"]["forecast"]["grid"] = sync_case["evcc"]["forecast"]["grid"][:12]
    report = tick(sync_case)
    assert report["errors"] == {}
    assert report["event"]["status"] == "waiting-publication"


def test_gap_in_cached_load_blocks_dispatch(sync_case, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    key = (sync_case["now"].replace(minute=0, second=0) + timedelta(hours=1)).isoformat()
    sync_case["series"]["loadforecast_power_w"].pop(key)
    report = tick(sync_case, write_eos=True)
    assert "loadforecast_power_w" in report["errors"]["event"]
    assert not writes(sync_case, "POST")


def test_two_processes_share_one_durable_event_claim(sync_case, monkeypatch):
    import multiprocessing
    from queue import Empty

    monkeypatch.setenv("DRY_RUN", "false")
    context = multiprocessing.get_context("fork")  # Runtime is a Linux container.
    queue = context.Queue()
    original = sync_case["http"]

    def http(url, **kwargs):
        if kwargs.get("method") == "POST":
            queue.put("post")
        return original(url, **kwargs)

    sync_case["http"] = http

    def worker():
        queue.put(tick(sync_case, write_eos=True)["event"]["status"])

    processes = [context.Process(target=worker) for _ in range(2)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        messages = []
        while True:
            try:
                messages.append(queue.get(timeout=.1))
            except Empty:
                break
        assert sorted(messages) == ["post", "succeeded", "succeeded"]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(2)
        queue.close()


def test_ha_update_after_cycle_start_is_not_future_dated(sync_case):
    observed = sync_case["now"] + timedelta(seconds=2)
    sync_case["ha"]["last_updated"] = observed.isoformat()
    report = tick(sync_case, clock=lambda: sync_case["now"] + timedelta(seconds=3))
    assert report["errors"] == {}
    assert report["soc"]["age_seconds"] == 1
    assert report["soc"]["source_timestamp"] == observed.isoformat()


def test_soc_expiring_during_preflight_blocks_post(sync_case, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    instant = [sync_case["now"]]
    original = sync_case["http"]

    def delayed(url, **kwargs):
        result = original(url, **kwargs)
        if "key=feed_in_tariff_wh" in url:
            instant[0] += timedelta(seconds=301)
        return result

    sync_case["http"] = delayed
    report = tick(sync_case, write_eos=True, clock=lambda: instant[0])
    assert "expired" in report["errors"]["event"]
    assert not writes(sync_case, "POST")

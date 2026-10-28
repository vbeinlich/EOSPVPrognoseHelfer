import copy
import json
from pathlib import Path

import jsonschema
import pytest

from eos_pv_helper.app import IMPORT_PATH, run_once, verify_contract
from eos_pv_helper.normalize import ForecastError


def source_reader(case):
    values = case[2]
    return lambda _: [{"timestamp": dt.isoformat(), "power_w": value}
                      for dt, value in values.items()]


def test_default_is_offline_dry_run(config, forecast_case):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline dry-run must not call any HTTP endpoint")
    payload, report = run_once(config, source_reader=source_reader(forecast_case), http=forbidden)
    assert len(payload["data"]) == 192
    assert report["mode"] == "dry-run"
    assert json.loads((Path(config["output"]["directory"]) / "health.json").read_text())["ok"]


@pytest.mark.parametrize("config_enable,flag", [(False, True), (True, False)])
def test_two_separate_write_opt_ins(config, forecast_case, config_enable, flag):
    config["eos"]["write_enabled"] = config_enable
    calls = []
    if flag:
        with pytest.raises(ForecastError, match="both"):
            run_once(config, write_eos=flag, source_reader=source_reader(forecast_case),
                     http=lambda *a, **kw: calls.append((a, kw)))
    else:
        run_once(config, write_eos=flag, source_reader=source_reader(forecast_case),
                 http=lambda *a, **kw: calls.append((a, kw)))
    assert not calls


def test_day_gap_prevents_even_the_first_http_request(config, forecast_case):
    config["eos"].update(url="http://127.0.0.1:8503", write_enabled=True)
    forecast_case[2].pop(next(iter(forecast_case[2])))
    calls = []
    with pytest.raises(ForecastError, match="daylight"):
        run_once(config, write_eos=True, source_reader=source_reader(forecast_case),
                 http=lambda *a, **kw: calls.append(a))
    assert calls == []


def test_payload_matches_the_live_captured_eos_contract(config, forecast_case, schema):
    payload, _ = run_once(config, source_reader=source_reader(forecast_case))
    jsonschema.Draft202012Validator(
        {"$ref": "#/components/schemas/PydanticDateTimeDataFrame", **schema}
    ).validate(payload)


def test_write_only_exact_provider_import_then_readback(config, forecast_case, schema, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    config["eos"].update(url="http://127.0.0.1:8503", write_enabled=True)
    calls, imported = [], {}

    def http(url, **kwargs):
        calls.append((url, kwargs.get("method", "GET")))
        if url.endswith("/openapi.json"):
            return schema
        if url.endswith("/v1/config"):
            return {"pvforecast": {"provider": "PVForecastImport", "pvforecastimport": {}}}
        if kwargs.get("method") == "PUT":
            assert url.endswith(IMPORT_PATH)
            imported.update(kwargs["payload"]["data"])
            return None
        return {"data": {key: row["pvforecast_ac_power"] for key, row in imported.items()}}

    _, report = run_once(config, write_eos=True, source_reader=source_reader(forecast_case), http=http)
    assert report["import_verified"]
    assert [url for url, method in calls if method != "GET"] == [
        "http://127.0.0.1:8503" + IMPORT_PATH
    ]
    assert len(calls) == 4


@pytest.mark.parametrize("provider,settings", [
    ("PVForecastPVLib", {}),
    ("PVForecastImport", {"import_json": "{}"}),
    ("PVForecastImport", {"import_file_path": "/some/file.json"}),
])
def test_provider_or_overwriting_import_configuration_is_never_changed(
    config, forecast_case, schema, provider, settings, monkeypatch
):
    monkeypatch.setenv("DRY_RUN", "false")
    config["eos"].update(url="http://127.0.0.1:8503", write_enabled=True)
    calls = []

    def http(url, **kwargs):
        calls.append(kwargs.get("method", "GET"))
        return schema if url.endswith("openapi.json") else {
            "pvforecast": {"provider": provider, "pvforecastimport": settings}}

    with pytest.raises(ForecastError):
        run_once(config, write_eos=True, source_reader=source_reader(forecast_case), http=http)
    assert "PUT" not in calls


def test_schema_mismatch_fails_even_if_generic_dict_would_accept_payload(schema):
    schema = copy.deepcopy(schema)
    schema["paths"]["/v1/prediction/import/{provider_id}"]["put"]["requestBody"][
        "content"]["application/json"]["schema"] = {"type": "object"}
    with pytest.raises(ForecastError, match="does not advertise"):
        verify_contract(schema)


def test_bad_readback_is_an_error_and_is_not_retried(config, forecast_case, schema, monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    config["eos"].update(url="http://127.0.0.1:8503", write_enabled=True)
    writes = []

    def http(url, **kwargs):
        if url.endswith("openapi.json"):
            return schema
        if url.endswith("/v1/config"):
            return {"pvforecast": {"provider": "PVForecastImport"}}
        if kwargs.get("method") == "PUT":
            writes.append(url)
        return {"data": {}}

    with pytest.raises(ForecastError, match="readback"):
        run_once(config, write_eos=True, source_reader=source_reader(forecast_case), http=http)
    assert len(writes) == 1


def test_pv_default_dry_run_environment_blocks_accidental_flag(config, forecast_case, monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    config["eos"].update(url="http://127.0.0.1:8503", write_enabled=True)
    with pytest.raises(ForecastError, match="DRY_RUN"):
        run_once(config, write_eos=True, source_reader=source_reader(forecast_case),
                 http=lambda *a, **kw: pytest.fail("No HTTP allowed after dry-run gate"))

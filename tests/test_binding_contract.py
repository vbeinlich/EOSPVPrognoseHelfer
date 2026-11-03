"""Independent negative evidence shared across all consumers, never optimizes."""

import copy
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from evidence_vectors import pack, vectors
from synthetic_binding import bind, sha

from eos_pv_helper import doctor, evidence, historical, plan_inspector
from eos_pv_helper.event_context import observed_options
from eos_pv_helper.inputs import day_ahead_version

NOW = datetime(2026, 10, 29, 13, 5, tzinfo=UTC)


def synthetic(now=NOW, *, zero_pv=False, soc=55.9):
    from zoneinfo import ZoneInfo
    origin = now.astimezone(ZoneInfo("Europe/Berlin")).replace(hour=0, minute=0, second=0).astimezone(UTC)
    start = origin + timedelta(hours=int((now-origin).total_seconds()/3600))
    prices = {"data": {(origin+timedelta(minutes=15*i)).isoformat():
        {"elecprice_marketprice_wh": -.0001+i*.000001} for i in range(480)}}
    forecast = {"data": {(origin+timedelta(minutes=15*i)).isoformat():
        {"pvforecast_ac_power": 0 if zero_pv else i*17 % 3011} for i in range(480)}}
    version = day_ahead_version(prices, now, "Europe/Berlin")
    claim = {**version, "start_utc": start.isoformat(), "claimed_at_utc": now.isoformat(),
        "control_hours": 24, "interval_seconds": 3600, "effective_tail_hours": 10, "status": "succeeded"}
    sample = {"usable": True, "source": "evcc", "freshness_verified": True,
        "source_timestamp": now.isoformat(), "percent": soc, "factor": soc/100,
        "timestamp_kind": "successful_uncached_device_read_lower_bound",
        "freshness_evidence": {"contract": "evcc-0.318.1/e3dc-rscp/uncached-getters",
            "live_soc_percent": soc, "live_power_w": -300,
            "read_started_at_utc": now.isoformat(), "read_completed_at_utc": now.isoformat()}}
    pv = {"checked_at_utc": now.isoformat(), "count": 480, "import_verified": True,
        "start_utc": origin.isoformat(), "end_exclusive_utc": (origin+timedelta(hours=120)).isoformat(),
        "source_fetched_at_utc": now.isoformat(), "source_max_age_seconds": 3600}
    values = {"sync-state.json": {"pv_import_verified": True, "events": {version["version"]: claim}},
        "sync-report.json": {"checked_at_utc": now.isoformat(), "mode": "write", "errors": {},
            "event": copy.deepcopy(claim), "soc": {**sample, "import_verified": True}, "pv": pv,
            "prices": {"count": 480, "unit": "EUR/Wh", "import_verified": True,
                "control_coverage": {"control_complete": True, "required_control_hours": 24}}},
        "prices.json": prices, "soc.json": sample, "forecast.json": forecast, "report.json": copy.deepcopy(pv),
        "solution-"+version["version"]+".json": {"interval_seconds": 3600,
            "start_solution_datetime": start.isoformat(), "ac_charge": [0]*24,
            "dc_charge": [1]*24, "discharge_allowed": [0]*24, "result": {"total_costs": 1.25}}}
    request = bind(values)
    solution = values["solution-"+version["version"]+".json"]
    observation = observed_options({})
    manifest = {"schema_version": 2, "event_version": version["version"],
        "captured_at_utc": now.isoformat(), "timezone": "Europe/Berlin",
        "configured_constraints_read": True,
        "validation_constraints": {"max_age_seconds": 300, "max_abs_power_w": 20000},
        "producer": {"contract": "eos-pv-helper/automatic-evidence-v1", "observed_options": observation,
            "observed_options_sha256": sha(observation), "dispatched_request_sha256": sha(request),
            "solution_inputs": historical.solution_inputs(solution)}}
    return historical.unpack(pack(manifest, values))


def consumers(tmp_path, raw, *, expected):
    manifest, files = historical.unpack(raw)
    now = historical.timestamp(manifest["captured_at_utc"])+timedelta(days=1)
    version = manifest["event_version"]
    path = tmp_path/"snapshot.zip"
    path.write_bytes(raw)
    root = tmp_path/"output"
    root.mkdir()
    (root/"genetic-evidence").mkdir()
    (root/"genetic-evidence"/(version+".zip")).write_bytes(raw)
    claim = json.loads(files["sync-state.json"])["events"][version]
    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}
    app, code = doctor.snapshot_acceptance(path, now=now)
    view = plan_inspector.archived_inputs(root, version, claim, files["solution-"+version+".json"], now)
    standalone = subprocess.run([sys.executable, "-I", "-S", "-B", historical.__file__,
        "--snapshot", str(path)], capture_output=True)
    assert b"Traceback" not in standalone.stderr
    if expected == "blocked":
        with pytest.raises(historical.ForecastError):
            historical.validate(manifest, files, now=now)
        with pytest.raises((evidence.EvidenceError, historical.ForecastError)):
            evidence.inspect_archive(root, {}, version, claim, hashlib.sha256(files["solution-"+version+".json"]).hexdigest(), lambda: now)
        assert code == standalone.returncode == 1 and app["accepted"] is False
        assert view["status"] == "unproven"
    else:
        shared = historical.validate(manifest, files, now=now)
        cli = json.loads(standalone.stdout)
        assert code == standalone.returncode == (0 if expected == "accepted" else 2)
        for result in (shared, app, cli):
            assert result["validation_contract"] == historical.VALIDATION_CONTRACT
            assert result["status"] == expected
            assert result["input_binding_complete"] is (expected == "accepted")
            assert result["runtime_context"]["exact_solver_options_proven"] is False
        assert view["status"] == ("verified" if expected == "accepted" else "legacy_limited")
        assert view["input_binding_complete"] is (expected == "accepted")
    assert before == {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.rglob("*") if p.is_file()}


NEGATIVES = [name for name, _ in vectors(*synthetic())]


@pytest.mark.parametrize("failure", NEGATIVES)
def test_every_consumer_rejects_same_rehashed_wrong_archive(tmp_path, failure):
    raw = dict(vectors(*synthetic()))[failure]
    consumers(tmp_path, raw, expected="blocked")


@pytest.mark.parametrize("when", [NOW, datetime(2026, 3, 29, 1, 5, tzinfo=UTC),
    datetime(2026, 10, 25, 0, 5, tzinfo=UTC), datetime(2026, 10, 25, 1, 5, tzinfo=UTC)])
@pytest.mark.parametrize("zero_pv", [False, True])
def test_midnight_request_run_relative_response_negative_prices_zero_pv_and_dst(tmp_path, when, zero_pv):
    m, f = synthetic(when, zero_pv=zero_pv)
    consumers(tmp_path, historical.pack(m, f), expected="accepted")


@pytest.mark.parametrize("soc", [0, 55.999, 100])
def test_float_rounding_and_integer_soc_quantization_are_bounded(tmp_path, soc):
    m, f = synthetic(soc=soc)
    values = {n: json.loads(raw) for n, raw in f.items()}
    s = values["solution-"+m["event_version"]+".json"]
    assert s["parameters"]["pv_battery"]["initial_soc_percentage"] == int(soc)
    for v in s["parameters"]["ems"]["pv_forecast_wh"]:
        assert v >= 0
    s["parameters"]["ems"]["pv_forecast_wh"][0] += 1e-7
    s["parameters"]["ems"]["electricity_price_per_wh"][0] += 1e-13
    m["producer"]["solution_inputs"] = historical.solution_inputs(s)
    consumers(tmp_path, pack(m, values), expected="accepted")


@pytest.mark.parametrize("minimal", [False, True])
def test_legacy_is_readable_but_never_complete_without_receipt(tmp_path, minimal):
    m, f = synthetic()
    values = {n: json.loads(raw) for n, raw in f.items()}
    del values["sync-report.json"]["event"]["request_binding"]
    m.pop("producer")
    if minimal:
        values["solution-"+m["event_version"]+".json"].pop("parameters")
    consumers(tmp_path, pack(m, values), expected="legacy_limited")


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'])
def test_ambiguous_or_nonfinite_original_json_is_rejected(raw):
    with pytest.raises(historical.ForecastError):
        historical.decode(raw)


def test_transport_manifest_and_ci_gates_are_current():
    from pathlib import Path

    from update_evidence_transports import update

    assert update()["validation_contract"] == historical.VALIDATION_CONTRACT
    workflow = (Path(__file__).resolve().parents[1]/".github/workflows/test.yaml").read_text()
    for required in ("actionlint@v1.7.7", "update_evidence_transports.py", "--user 10001:10001",
                     "tests/test_binding_contract.py", "review/pr22_contract_probe.py"):
        assert required in workflow


def test_real_http_serialization_matches_receipt_without_network(monkeypatch):
    import io
    from types import SimpleNamespace

    from eos_pv_helper import app

    m, f = synthetic()
    receipt = json.loads(f["sync-report.json"])["event"]["request_binding"]
    captured = []
    def open_request(request, **kwargs):
        captured.append(request)
        response = io.BytesIO(b'{"mocked":true}')
        response.headers = {}
        return response
    monkeypatch.setattr(app, "build_opener", lambda *args: SimpleNamespace(open=open_request))
    result = app.request_json("http://127.0.0.1:8503/v1/optimize", method="POST", payload=receipt["request"])
    assert result == {"mocked": True} and len(captured) == 1
    decoded_wire = json.loads(captured[0].data)
    assert decoded_wire == receipt["request"]
    assert sha(decoded_wire) == receipt["request_sha256"]

"""Pure stdlib reader checks; rehashed negative cases must also be rejected."""

import copy
import hashlib
import json
import socket
from pathlib import Path

import pytest

from eos_pv_helper import dashboard, economics_native
from eos_pv_helper import replay_contract as contract

FIXTURES = Path(__file__).parent / "fixtures"


def sample():
    raw = (FIXTURES / "replay-synthetic-solution.json").read_bytes()
    return (
        raw,
        json.loads(raw),
        json.loads((FIXTURES / "replay-synthetic-sidecar.json").read_bytes()),
    )


def reseal(value):
    value["plans"] = [
        contract.seal({k: v for k, v in p.items() if k != "sha256"}) for p in value["plans"]
    ]
    return contract.seal({k: v for k, v in value.items() if k != "sha256"})


def test_valid_sidecar_uses_internal_storage_energy_and_original_byte_binding(monkeypatch):
    raw, solution, catalog = sample()
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: pytest.fail("Network forbidden"))
    monkeypatch.setattr(
        economics_native, "simulate", lambda *a, **kw: pytest.fail("Reader must not replay")
    )
    plan = contract.validate(
        contract.decode(contract.canonical(catalog))["plans"][0], raw, solution
    )
    assert plan["source_solution_sha256"] == hashlib.sha256(raw).hexdigest()
    assert plan["energy_basis"] == "internal_storage_wh"
    assert plan["summary"]["equivalent_full_cycles"] == pytest.approx(
        sum(s["discharge_internal_wh"] for s in plan["slots"]) / plan["usable_capacity_wh"]
    )
    assert plan["slots"][0]["pv_charge_internal_wh"] > 0
    assert plan["slots"][0]["grid_charge_internal_wh"] > 0
    assert plan["slots"][0]["discharge_internal_wh"] > plan["slots"][0]["discharge_dc_output_wh"]
    assert plan["summary"]["charge_windows"] and plan["summary"]["discharge_windows"]


def test_cross_interpreter_summary_roundoff_is_accepted():
    raw, solution, value = sample()
    value["plans"][0]["summary"]["charge_internal_wh"] += 1e-10
    value = reseal(value)
    contract.validate(value["plans"][0], raw, solution)


@pytest.mark.parametrize(
    "case",
    [
        "bytes",
        "params",
        "projection",
        "revision",
        "source_hash",
        "dependencies",
        "time",
        "interval",
        "index",
        "basis",
        "negative",
        "nan",
        "pv",
        "grid",
        "sum",
        "discharge",
        "soc",
        "efc",
        "capacity",
        "windows",
        "summary",
        "result",
        "proof",
        "traced",
        "tolerance",
        "slot_count",
        "end_soc",
        "extra",
    ],
)
def test_rehashed_broken_sidecars_fail_closed(case):
    raw, solution, catalog = sample()
    catalog = copy.deepcopy(catalog)
    p = catalog["plans"][0]
    s = p["slots"][0]
    if case == "bytes":
        raw += b" "
    elif case == "params":
        solution["parameters"]["extra"] = "changed"
    elif case == "projection":
        p["projection_sha256"] = "a" * 64
    elif case == "revision":
        p["engine"]["expected_source_revision"] = "a" * 40
    elif case == "source_hash":
        p["engine"]["source_sha256"]["devices/genetic/battery.py"] = "a" * 64
    elif case == "dependencies":
        p["engine"]["dependencies"] = {}
    elif case == "time":
        p["start_utc"] = "2026-10-29T00:00:00+00:00"
    elif case == "interval":
        p["interval_seconds"] = 900
    elif case == "index":
        s["source_index"] = 5
    elif case == "basis":
        p["energy_basis"] = "battery_dc"
    elif case == "negative":
        s["charge_internal_wh"] = -1
    elif case == "nan":
        s["charge_internal_wh"] = float("nan")
    elif case == "pv":
        s["pv_charge_internal_wh"] += 1
    elif case == "grid":
        s["grid_charge_dc_input_wh"] += 1
    elif case == "sum":
        s["charge_dc_input_wh"] += 1
    elif case == "discharge":
        s["discharge_internal_wh"] += 1
    elif case == "soc":
        s["soc_start_percent"] += 1
    elif case == "efc":
        s["equivalent_full_cycles"] += 1
    elif case == "capacity":
        p["usable_capacity_wh"] += 1
    elif case == "windows":
        p["summary"]["charge_windows"] = []
    elif case == "summary":
        p["summary"]["charge_internal_wh"] += 1
    elif case == "result":
        p["replay"]["result"]["costs_per_hour"][0] += 1
    elif case == "proof":
        p["proof"]["historical_measurement"] = True
    elif case == "traced":
        p["replay"]["instrumentation_identical"] = False
    elif case == "tolerance":
        p["replay"]["tolerance"]["absolute"] = 1
    elif case == "slot_count":
        p["slots"].pop()
    elif case == "end_soc":
        p["replay"]["end_soc_percent"] += 1
    elif case == "extra":
        p["replay"]["extra_result"] = {"unmatched_field": [0]}
    with pytest.raises((ValueError, KeyError, TypeError)):
        catalog = reseal(catalog)
        contract.validate(contract.decode(contract.canonical(catalog))["plans"][0], raw, solution)


@pytest.mark.parametrize("case", ["hash", "version", "duplicate"])
def test_catalog_integrity_and_versions(case):
    _, _, value = sample()
    if case == "hash":
        value["sha256"] = "a" * 64
    elif case == "version":
        value["schema_version"] = 2
        value = reseal(value)
    else:
        value["plans"].append(copy.deepcopy(value["plans"][0]))
        value = reseal(value)
    with pytest.raises(ValueError):
        contract.decode(contract.canonical(value))


def test_private_original_input_mode_keeps_claims_unproven_and_preserves_last_good(tmp_path):
    raw, _, value = sample()
    source = tmp_path / "source.json"
    source.write_bytes(raw)
    replay = tmp_path / "replay.json"
    replay.write_bytes(contract.canonical(value))
    output = tmp_path / "site"
    output.mkdir()
    assert dashboard.refresh(None, output, solutions=[source], replay_file=replay)
    html = (output / "index.html").read_text()
    report = json.loads(dashboard.DATA_PATTERN.search(html)[1])
    p = report["plans"][0]
    assert p["claim_status"] == "unmatched"
    assert p["rows"][0]["flow"]["proof"] == "posthoc_native_model_replay"
    expected = value["plans"][0]["slots"][0]
    assert p["rows"][0]["flow"]["pv_wh"] == expected["pv_charge_internal_wh"]
    assert p["rows"][0]["flow"]["pv_wh"] != expected["pv_charge_dc_input_wh"]
    assert report["model_ranges"]["7"] and not report["ranges"]["7"]
    replay.write_text('{"truncated":')
    assert not dashboard.refresh(None, output, solutions=[source], replay_file=replay)
    fallback = json.loads(dashboard.DATA_PATTERN.search((output / "index.html").read_text())[1])
    assert fallback["plans"] == report["plans"] and fallback["update_error"]
    assert source.read_bytes() == raw


def test_bundle_excludes_exporter_and_includes_only_validator():
    import io
    import zipfile

    from build_ems_dashboard import build

    with zipfile.ZipFile(io.BytesIO(build())) as z:
        assert "eos_pv_helper/replay_contract.py" in z.namelist()
        assert "eos_pv_helper/replay_export.py" not in z.namelist()

"""Native fixed-control producer, physical scopes, no optimizer and no originals changed."""

import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from eos_pv_helper import economics, replay_contract, replay_export  # noqa: E402

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_native_export_reproduces_pv_and_grid_split_without_mutating_input(tmp_path):
    raw = (FIXTURES / "replay-synthetic-solution.json").read_bytes()
    source = tmp_path / "source.json"
    source.write_bytes(raw)
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    output = tmp_path / "replays.json"
    catalog = replay_export.export([source], output)
    p = replay_contract.validate(catalog["plans"][0], raw, json.loads(raw))
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert p["engine"]["optimizer_invoked"] is False
    assert (
        p["slots"][0]["pv_charge_internal_wh"] > 0 and p["slots"][0]["grid_charge_internal_wh"] > 0
    )
    assert p["slots"][0]["discharge_internal_wh"] > 0
    assert sum(s["discharge_internal_wh"] for s in p["slots"]) == pytest.approx(
        sum(s["discharge_dc_output_wh"] for s in p["slots"]) / 0.85
    )
    assert p["summary"]["equivalent_full_cycles"] != pytest.approx(
        sum(s["discharge_dc_output_wh"] for s in p["slots"]) / p["usable_capacity_wh"]
    )
    with pytest.raises(ValueError):
        replay_export.export([source], output)
    with pytest.raises(ValueError):
        replay_export.export([source], source)


def test_mismatching_original_result_produces_no_sidecar(tmp_path):
    solution = json.loads((FIXTURES / "replay-synthetic-solution.json").read_bytes())
    solution["result"]["total_costs"] += 0.01
    source = tmp_path / "source.json"
    source.write_text(json.dumps(solution))
    output = tmp_path / "replays.json"
    with pytest.raises(economics.ComparisonError):
        replay_export.export([source], output)
    assert not output.exists()


def test_tracing_disagreement_fails_closed(monkeypatch):
    raw = (FIXTURES / "replay-synthetic-solution.json").read_bytes()
    from eos_pv_helper import economics_native

    original = economics_native.simulate
    calls = []

    def altered(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(1)
        if len(calls) == 2:
            result = copy.deepcopy(result)
            result["slots"][0]["battery_charge_dc_wh"] += 1
        return result

    monkeypatch.setattr(economics_native, "simulate", altered)
    with pytest.raises(ValueError):
        replay_export.create_plan(raw)


def test_corrupt_additional_load_result_is_rejected(tmp_path):
    solution = json.loads((FIXTURES / "replay-synthetic-solution.json").read_bytes())
    solution["result"]["load_wh_per_hour"] = [1] * len(solution["ac_charge"])
    source = tmp_path / "source.json"
    source.write_text(json.dumps(solution))
    output = tmp_path / "replays.json"
    with pytest.raises(ValueError):
        replay_export.export([source], output)
    assert not output.exists()

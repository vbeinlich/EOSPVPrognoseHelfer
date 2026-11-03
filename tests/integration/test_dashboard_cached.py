"""A saved native comparison may be displayed; the dashboard never computes one."""

import copy
import hashlib
import json
from datetime import UTC, datetime

import pytest

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from test_dashboard import packet as read_dashboard  # noqa: E402
from test_dashboard_wrapper import harness  # noqa: E402, F401
from test_economics import saved  # noqa: E402

from eos_pv_helper import dashboard, economics, plan_inspector  # noqa: E402
from eos_pv_helper.economics_native import simulate  # noqa: E402


@pytest.fixture
def cached(monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from requests.sessions import Session

    def forbidden(*a, **kw):
        pytest.fail("Optimizer and HTTP forbidden")

    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)
    solution = saved()
    raw = json.dumps(solution).encode()
    version = "a" * 64
    plan = plan_inspector.parse_plan(
        None,
        version,
        raw,
        {
            "version": version,
            "status": "succeeded",
            "start_utc": solution["start_solution_datetime"],
            "interval_seconds": 3600,
            "control_hours": 24,
        },
        __import__("zoneinfo").ZoneInfo("Europe/Berlin"),
        None,
        datetime.now(UTC),
        archive_lookup=False,
    )
    comparison = economics.compare(economics.project(solution), runner=simulate)
    assert comparison["status"] == "calculated"
    packet = {
        "plans": [{"solution_sha256": hashlib.sha256(raw).hexdigest(), "comparison": comparison}]
    }
    # Once the cache exists, even the native forward replay is forbidden in the reader.
    monkeypatch.setattr(economics, "evaluate", forbidden)
    return plan, solution, packet


def test_saved_comparison_accepts_same_bytes_inputs_engine_and_fair_end_value(cached):
    plan, solution, packet = cached
    result = dashboard.saved_comparison(plan, solution, packet)
    assert result["status"] == "cached_native_replay"
    assert result["advantage_eur"] == pytest.approx(0, abs=1e-8)
    assert result["baseline_eur"] == pytest.approx(6.03)
    assert result["genetic_eur"] == pytest.approx(6.03)


@pytest.mark.parametrize(
    "mutation", ["source", "inputs", "engine", "saving", "price", "slot", "end_value", "nan"]
)
def test_wrong_or_inconsistent_comparison_never_becomes_an_advantage(cached, mutation):
    plan, solution, packet = cached
    packet = copy.deepcopy(packet)
    entry = packet["plans"][0]
    c = entry["comparison"]
    if mutation == "source":
        entry["solution_sha256"] = "b" * 64
    elif mutation == "inputs":
        c["input_sha256"] = "b" * 64
    elif mutation == "engine":
        c["engine"]["source_sha256"]["devices/genetic/battery.py"] = "b" * 64
    elif mutation == "saving":
        c["additional_savings_eur"] = 100
    elif mutation == "price":
        c["slots"]["baseline"][0]["grid_cost_eur"] = 100
    elif mutation == "slot":
        c["slots"]["baseline"][0]["interval_seconds"] = 900
    elif mutation == "end_value":
        c["baseline"]["adjusted_cost_eur"] = 100
    else:
        c["slots"]["baseline"][0]["grid_import_wh"] = float("nan")
    assert dashboard.saved_comparison(plan, solution, packet)["advantage_eur"] is None


def test_unraid_wrapper_uses_explicit_precomputed_report_without_running_engine(
    harness, cached, tmp_path  # noqa: F811
):
    source, dest, _, run = harness
    _, solution, cache = cached
    state = json.loads((source / "sync-state.json").read_text())
    version = max(state["events"], key=lambda v: state["events"][v]["start_utc"])
    raw = json.dumps(solution).encode()
    (source / f"solution-{version}.json").write_bytes(raw)
    state["events"][version]["interval_seconds"] = 3600
    (source / "sync-state.json").write_text(json.dumps(state))
    cache["plans"][0]["solution_sha256"] = hashlib.sha256(raw).hexdigest()
    cache_path = tmp_path / "economics.json"
    cache_path.write_text(json.dumps(cache))
    assert run(extra=(str(cache_path),)).returncode == 0
    result = read_dashboard(dest / "index.html")["plans"][0]["model_comparison"]
    assert result["status"] == "cached_native_replay"
    assert result["advantage_eur"] == pytest.approx(0, abs=1e-8)

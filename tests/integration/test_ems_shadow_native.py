"""Pinned native forward simulation, synthetic actuals, no search or HTTP."""

import pytest

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from test_ems_shadow import AS_OF, context, fixture  # noqa: E402

from eos_pv_helper import economics as cost  # noqa: E402
from eos_pv_helper import economics_native as native  # noqa: E402
from eos_pv_helper import ems_shadow as shadow  # noqa: E402


@pytest.fixture(autouse=True)
def forbid_optimization_and_network(monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from requests.sessions import Session

    def forbidden(*a, **kw):
        pytest.fail("Offline shadow attempted optimizer or HTTP")
    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)


def test_native_model_on_complete_synthetic_actuals(tmp_path):
    tmp_path.chmod(0o700)
    original, export = fixture(runner=native.simulate)
    actuals, conditions = context(original, export)
    result = shadow.batch([{"raw": cost.canonical(original), "binding": {}, "synthetic": True}],
                          actuals, conditions, tmp_path, as_of=AS_OF)
    run = result["results"][0]
    assert run["status"] == "SYNTHETIC_COMPARABLE", run["reasons"]
    assert run["forecast_replay"]["engine"]["optimizer_invoked"] is False
    assert run["forecast_replay"]["engine"]["expected_source_revision"] == native.EOS_REVISION
    assert run["actual_input_reference"]["summary"]["grid_import_wh"]["delta_kwh"] == pytest.approx(0)
    assert run["costs"]["hypothetical_B_minus_C_eur"] == pytest.approx(0, abs=1e-9)
    assert run["costs"]["A_metered_cost_eur"] == pytest.approx(6.03)


def test_thirty_days_native_replays_are_repeatable_and_explicitly_synthetic(tmp_path):
    from datetime import timedelta

    tmp_path.chmod(0o700)
    runs = []
    for i in range(30):
        original, export = fixture(start=AS_OF-timedelta(days=30-i), runner=native.simulate)
        actuals, conditions = context(original, export)
        run = shadow.evaluate(cost.canonical(original), {}, actuals, conditions,
                              as_of=AS_OF, synthetic=True)
        assert run["status"] == "SYNTHETIC_COMPARABLE", run["reasons"]
        runs.append(run)
    report = shadow.ranges(runs, AS_OF)
    for days, hours in (("1", 24), ("7", 168), ("30", 720)):
        assert report[days]["status"] == "COMPLETE"
        assert report[days]["coverage_hours"] == hours
        assert report[days]["synthetic_only"] is True
        assert report[days]["realized_savings_eur"] is None
    assert report["30"]["actual_grid_purchase_calculated_eur"] == pytest.approx(30*6.03)


def test_native_cli_uses_private_config_and_never_changes_source(tmp_path):
    import json
    import subprocess
    import sys

    original, export = fixture(runner=native.simulate)
    _, conditions = context(original, export)
    paths = [tmp_path / name for name in ("original.json", "actuals.json", "conditions.json")]
    for path, value in zip(paths, (original, export, conditions), strict=True):
        path.write_bytes(cost.canonical(value))
    before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
    output = tmp_path / "output"
    output.mkdir(mode=0o700)
    completed = subprocess.run([sys.executable, "-m", "eos_pv_helper.ems_shadow", "--solution", str(paths[0]),
        "--actuals", str(paths[1]), "--conditions", str(paths[2]), "--output", str(output),
        "--as-of", AS_OF.isoformat()], capture_output=True, timeout=60)
    assert completed.returncode == 2, completed.stderr.decode()
    report = json.loads((output / "report.json").read_bytes())
    assert report["results"][0]["status"] == "SYNTHETIC_COMPARABLE"
    assert report["optimizer_invoked"] is False
    assert (output / "native-runtime/EOS.config.json").is_file()
    assert not (tmp_path / "EOS.config.json").exists()
    assert before == [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]

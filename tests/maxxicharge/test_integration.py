import base64
import copy
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from dashboard_fixture import make as dashboard_fixture
from maxxicharge_fixture import make

from ems_maxxicharge.__main__ import main
from ems_maxxicharge.config import Config
from ems_maxxicharge.engine import simulate
from ems_maxxicharge.inputs import canonical
from eos_pv_helper import dashboard, dashboard_view

PROJECT = Path(__file__).resolve().parents[2]


def test_cli_immutable_outputs_hashes_and_no_source_modifications(tmp_path, monkeypatch):
    data = make(days=1)
    source = tmp_path / "input.json"
    source.write_bytes(canonical(data))
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    output = tmp_path / "run"
    monkeypatch.setattr("socket.socket", lambda *a, **kw: pytest.fail("Network forbidden"))
    assert main(["--input", str(source), "--output", str(output)]) == 0
    assert before == (source.read_bytes(), source.stat().st_mtime_ns)
    manifest = json.loads((output / "manifest.json").read_bytes())
    assert manifest["complete"] is True
    for name, expected in manifest["artifacts_sha256"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected
    old = (output / "simulation.json").read_bytes()
    assert main(["--input", str(source), "--output", str(output)]) == 2
    assert (output / "simulation.json").read_bytes() == old
    html = (output / "index.html").read_text()
    assert "SIM" in html and "MaxxiCharge" in html


def test_cli_invalid_inputs_leave_no_report_directory(tmp_path):
    source = tmp_path / "input.json"
    source.write_bytes(canonical(make()))
    output = tmp_path / "run"
    config = tmp_path / "bad.json"
    config.write_text('{"mqtt_host":"forbidden"}')
    assert main(["--input", str(source), "--config", str(config), "--output", str(output)]) == 2
    assert not output.exists()


def test_existing_dashboard_optional_simulation_and_last_good_recovery(tmp_path):
    source = dashboard_fixture(tmp_path / "source")
    sim = tmp_path / "simulation.json"
    sim.write_bytes(canonical(simulate(make(days=1), Config())))
    plain, valid = dashboard.render_refresh(source)
    assert valid
    plain_data = json.loads(dashboard.DATA_PATTERN.search(plain)[1])
    assert "maxxicharge_sim" not in plain_data
    html, valid = dashboard.render_refresh(source, simulation_file=sim)
    assert valid
    data = json.loads(dashboard.DATA_PATTERN.search(html)[1])
    assert data["maxxicharge_sim"]["mode"] == "SIM"
    assert data["plans"] == plain_data["plans"]
    sim.write_text('{"mode":"REAL"}')
    recovered, valid = dashboard.render_refresh(source, html, simulation_file=sim)
    assert not valid
    last = json.loads(dashboard.DATA_PATTERN.search(recovered)[1])
    assert last["maxxicharge_sim"] == data["maxxicharge_sim"]
    assert last["update_error"] is True


def test_dashboard_csp_covers_script_and_escapes_injected_text():
    sim = simulate(make(days=1), Config())
    sim["assumptions"].append('</script><script>alert("no")</script>')
    html = dashboard_view.render({"plans": [], "maxxicharge_sim": sim})
    assert '</script><script>alert("no")' not in html
    script = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
    expected = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    assert "script-src 'sha256-" + expected + "'" in html
    assert "connect-src 'none'" in html
    assert "fetch(" not in script


@pytest.mark.parametrize("mutation", ["real", "nan", "command", "missing", "rows",
    "summary", "time", "power", "soc"])
def test_bad_sim_reports_rejected(mutation):
    sim = simulate(make(days=1), Config())
    if mutation == "real":
        sim["mode"] = "REAL"
    elif mutation == "nan":
        sim["scenarios"]["e3dc"]["summary"]["losses_wh"] = float("nan")
    elif mutation == "command":
        sim["devices_commanded"] = True
    elif mutation == "missing":
        del sim["scenarios"]["e3dc"]
    elif mutation == "rows":
        sim["scenarios"]["e3dc"]["rows"] = []
    elif mutation == "summary":
        sim["scenarios"]["pv2_bat5"]["summary"]["grid_import_wh"] = "unknown"
    elif mutation == "time":
        sim["scenarios"]["pv2_bat5"]["rows"][0]["start_utc"] = "invalid"
    elif mutation == "power":
        sim["scenarios"]["pv2_bat5"]["rows"][0]["maxxi"]["discharge_w"] = 900
    else:
        sim["scenarios"]["pv2_bat5"]["rows"][0]["maxxi"]["soc_percent"] = None
    with pytest.raises(ValueError):
        dashboard_view.validate_sim_report(sim)


def test_compose_is_separate_offline_and_unprivileged():
    compose = yaml.safe_load((PROJECT / "simulator/compose.yaml").read_text())
    assert set(compose["services"]) == {"ems-maxxicharge-simulator"}
    service = compose["services"]["ems-maxxicharge-simulator"]
    assert service["network_mode"] == "none"
    assert service["read_only"] is True
    assert service["user"] == "10001:10001"
    assert service["restart"] == "no"
    assert service["cap_drop"] == ["ALL"]
    assert service["security_opt"] == ["no-new-privileges:true"]
    assert not any(k in service for k in ("ports", "devices", "privileged", "depends_on"))
    assert service["volumes"][0]["read_only"] is True
    assert "docker.sock" not in canonical(service).decode()
    dockerfile = (PROJECT / "simulator/Dockerfile").read_text()
    assert "sync.py" not in dockerfile and "app.py" not in dockerfile


def test_full_year_economic_math_on_artificial_measured_contract():
    # Entirely artificial analytic fixture, never a claim of available real history.
    # Constant load/PV makes the annual cost delta hand-calculable.
    data = make(days=1, seconds=3600)
    data["data_kind"] = "measured"
    data["e3dc"]["initial_soc_percent"] = 10
    data["pv_source"] = {"mode": "cached_planes"}
    prototype = copy.deepcopy(data["rows"][0])
    prototype.update(load_wh=1000, base_pv_wh=0, import_eur_kwh=.3, export_eur_kwh=.08)
    prototype["planes"] = {name: {"basis": "ac_equivalent_front_wh_per_kwp",
        "wh_per_kwp": 100, "tilt_deg": tilt, "azimuth_deg": 180}
        for name, tilt in (("suedhuette", 14), ("suedzaun", 90))}
    start = datetime(2025, 1, 1, tzinfo=UTC)
    data["rows"] = [{**prototype, "start_utc": (start + timedelta(hours=i)).isoformat(),
                     "end_utc": (start + timedelta(hours=i + 1)).isoformat()}
                    for i in range(8760)]
    report = simulate(data, Config(grid_charging_enabled=False, representative_year_confirmed=True,
        investments_eur={"pv2_bat5": 2000}, annual_maintenance_eur={"pv2_bat5": 20}))
    sums = report["scenarios"]["pv2_bat5"]["summary"]
    expected = .2 * .3 * 8760 - 20
    assert sums["annualized_savings_eur"] == pytest.approx(expected)
    assert sums["payback_years"] == pytest.approx(2000 / expected)
    assert sums["additional_self_consumption_wh"] == pytest.approx(200 * 8760)


def test_production_control_sources_unchanged_from_frozen_base():
    # Explicit hashes captured from the baseline; the simulator cannot alter the
    # existing execution path, deployed compose or hardware activation gates.
    hashes = json.loads((PROJECT / "simulator/production-baseline.json").read_text())
    for name, expected in hashes.items():
        assert hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() == expected

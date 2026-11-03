"""Combined PR #10/#13/#14/#15 pipeline, mocked dispatch and native forward replay only."""

import copy
import hashlib
import json
from datetime import timedelta

import pytest

pytest.importorskip("akkudoktoreos.optimization.genetic.genetic")

from test_economics import saved  # noqa: E402
from test_evidence import archive, build_case, tick  # noqa: E402
from test_plan_actual import measured  # noqa: E402

from eos_pv_helper import (  # noqa: E402
    economics,
    economics_native,
    economics_report,
    evidence,
    historical,
    plan_inspector,
)
from eos_pv_helper.plan_actual import Actuals  # noqa: E402


def test_archive_doctor_inspector_economics_actuals_after_waiting(config, monkeypatch):
    from akkudoktoreos.optimization.genetic.genetic import GeneticOptimization
    from requests.sessions import Session

    def forbidden(*a, **kw):
        pytest.fail("No network or native optimizer in the combined pipeline")
    monkeypatch.setattr(GeneticOptimization, "optimize_ems", forbidden)
    monkeypatch.setattr(Session, "request", forbidden)
    case = build_case(config, monkeypatch)
    case["settings"]["load"] = {"provider": "LoadAkkudoktor", "loadakkudoktor": {
        "loadakkudoktor_year_energy_kwh": 11251}}
    monkeypatch.setenv("DRY_RUN", "false")
    original_capture = evidence.capture_inputs
    captured = {}
    def capture(*args):
        captured["plan"], captured["series"] = copy.deepcopy(args[4]), copy.deepcopy(args[3])
        return original_capture(*args)
    monkeypatch.setattr("eos_pv_helper.sync.capture_inputs", capture)
    original_http = case["http"]
    def http(url, **kw):
        response = original_http(url, **kw)
        if not url.endswith("/v1/optimize"):
            return response
        plan, series = captured["plan"], captured["series"]
        start = historical.timestamp(plan["start_utc"])
        slots = int(plan["control_hours"]+plan["effective_tail_hours"])
        def average(key):
            return historical.interval_averages({historical.timestamp(k) if isinstance(k, str) else k: v
                                                for k, v in series[key].items()},
                                                start, slots, 3600)
        s = saved()
        s["start_solution_datetime"] = start.isoformat()
        s["parameters"]["pv_battery"]["initial_soc_percentage"] = 55
        s["parameters"]["pv_battery"]["device_id"] = "e3dc_s10e_pro"
        s["parameters"]["inverter"]["battery_id"] = "e3dc_s10e_pro"
        s["parameters"]["ems"].update(pv_forecast_wh=average("pvforecast_ac_power"),
            total_load=average("loadforecast_power_w"), electricity_price_per_wh=average("elecprice_marketprice_wh"),
            feed_in_tariff_per_wh=average("feed_in_tariff_wh"))
        s["discharge_allowed"] = [1]*24
        s["result"]["electricity_price"] = s["parameters"]["ems"]["electricity_price_per_wh"][:24]
        s["result"]["feed_in_tariff"] = s["parameters"]["ems"]["feed_in_tariff_per_wh"][:24]
        replay = economics_native.simulate(economics.project(s), baseline=False, load_scale=1)
        s["result"] = replay["result"]
        s["terminal_value"].update(battery_energy_wh=replay["end_usable_ac_wh"],
            credited_euro=economics.terminal_value(s["terminal_value"]["curve"], replay["end_usable_ac_wh"]),
            effective_tail_hours=plan["effective_tail_hours"])
        return s
    case["http"] = http
    result = tick(case)
    assert result["event"]["status"] == "succeeded", result["errors"]
    path = archive(case)
    original = path.read_bytes()
    manifest, files = historical.unpack(original)
    assert historical.validate(manifest, files, now=case["now"])["accepted"]
    assert manifest["producer"]["solution_inputs"]["selected_model_inputs_present"]
    assert manifest["producer"]["observed_options"]["annual_load_kwh"] == 11251
    assert manifest["producer"]["solution_inputs"]["annual_load_exact_binding"] == "not_reported_by_solution"
    root = path.parent.parent
    packet = plan_inspector.collect(root, now=case["now"], replay_inputs=True)
    assert packet["plans"][0]["inputs"]["status"] == "verified"
    actuals = Actuals(json.dumps(measured(start=historical.timestamp(captured["plan"]["start_utc"]), count=96)).encode(),
                      now=case["now"]+timedelta(days=2))  # Explicit synthetic historical evaluation clock.
    report = economics_report.from_packet(packet, actuals=actuals)
    assert report["plans"][0]["comparison"]["status"] == "calculated"
    assert report["plans"][0]["actuals"]["cash_coverage_complete"]
    assert report["plans"][0]["actuals"]["realized_savings_eur"] is None
    cutoff = (case["now"].replace(hour=0, minute=0, second=0)+timedelta(days=1)).timestamp()
    case["evcc"]["forecast"]["grid"] = [r for r in case["evcc"]["forecast"]["grid"] if r[0] < cutoff]
    assert tick(case)["event"]["status"] == "waiting-publication"
    assert hashlib.sha256(path.read_bytes()).digest() == hashlib.sha256(original).digest()
    later = plan_inspector.collect(root, now=case["now"], replay_inputs=True)
    assert later["latest_sync_status"] == "waiting-publication"
    assert economics_report.from_packet(later)["plans"][0]["comparison"]["status"] == "calculated"
    assert len([c for c in case["calls"] if c[0] == "POST"]) == 1

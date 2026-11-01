import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from test_economics import saved

from eos_pv_helper.economics import digest, project
from eos_pv_helper.plan_actual import Actuals, ActualsError, analyze, stamp


def measured(*, start=datetime(2026, 10, 31, 12, tzinfo=UTC), count=4):
    energy, tariffs, soc = [], [], []
    for i in range(count):
        a, b = start+timedelta(minutes=15*i), start+timedelta(minutes=15*(i+1))
        energy.append({"start_utc": a.isoformat(), "end_utc": b.isoformat(), "pv_wh": 0,
            "load_wh": 250, "grid_import_wh": 250, "grid_export_wh": 0,
            "battery_charge_dc_wh": 0, "battery_discharge_dc_wh": 0})
        tariffs.append({"start_utc": a.isoformat(), "end_utc": b.isoformat(), "retail_eur_kwh": .1+i*.1})
        soc.append({"at_utc": b.isoformat(), "percent": 40})
    return {"schema_version": 1, "energy_kind": "measured_interval_wh",
        "origin": {"kind": "homeassistant_statistics_export", "source_artifact_sha256": "a"*64,
            "pv_basis": "ac", "battery_basis": "dc_bus", "house_load_scope": "whole_site_including_loadpoints",
            "tariff_basis": "retail_final_eur_kwh"}, "energy": energy, "tariffs": tariffs, "soc": soc}


def actuals(data):
    return Actuals(json.dumps(data).encode())


def prediction(data):
    # Known synthetic model output; no simulation or inferred real battery energy.
    p = project(saved(count=1))
    slot = {"start_utc": p["start_utc"], "interval_seconds": 3600, "pv_wh": 0, "load_wh": 1000,
        "grid_import_wh": 1000, "grid_export_wh": 0, "soc_end_percent": 40, "grid_cost_eur": .3,
        "battery_charge_dc_wh": 0, "battery_discharge_dc_wh": 0}
    return p, {"status": "calculated", "input_sha256": digest(p), "slots": {"genetic": [slot], "baseline": [slot.copy()]}}


def test_measured_cash_uses_interval_energy_times_matching_final_price():
    m = actuals(measured())
    start = stamp("2026-10-31T13:00:00+01:00")
    assert m.total("grid_import_wh", start, start+timedelta(hours=1)) == 1000
    assert m.cash_cost(start, start+timedelta(hours=1)) == pytest.approx(.25)
    p, c = prediction(None)
    result = analyze(p, c, m)
    assert result["actual_grid_cash_cost_eur"] == pytest.approx(.25)
    assert result["realized_savings_eur"] is None
    assert result["rows"][0]["metrics"]["grid_cost_eur"]["delta_actual_minus_plan"] == pytest.approx(-.05)
    assert "not_attributable" in result["interpretation"]["grid_and_battery"]


@pytest.mark.parametrize("problem", ["gap", "missing-energy", "missing-price", "wrong-unit", "wrong-battery-basis", "excluded-loadpoints"])
def test_gaps_units_and_load_scope_do_not_become_zero(problem):
    data = measured()
    if problem == "gap":
        data["energy"].pop(1)
    elif problem == "missing-energy":
        data["energy"][0].pop("grid_import_wh")
    elif problem == "missing-price":
        data["tariffs"].pop(1)
    elif problem == "wrong-unit":
        data["origin"]["tariff_basis"] = "market_net_eur_mwh"
    elif problem == "wrong-battery-basis":
        data["origin"]["battery_basis"] = "ac_unknown_conversion"
    else:
        data["origin"]["house_load_scope"] = "excluding_loadpoints"
    p, c = prediction(None)
    r = analyze(p, c, actuals(data))
    if problem == "wrong-battery-basis":
        assert r["rows"][0]["metrics"]["battery_charge_dc_wh"]["actual"] is None
    elif problem == "excluded-loadpoints":
        assert r["rows"][0]["metrics"]["load_wh"]["actual"] is None
    else:
        assert r["actual_grid_cash_cost_eur"] is None and not r["cash_coverage_complete"]


def test_coarse_energy_is_not_split_or_repriced_across_variable_tariffs():
    d = measured()
    first = d["energy"][0]
    d["energy"] = [{**first, "end_utc": d["energy"][-1]["end_utc"], "grid_import_wh": 1000}]
    m = actuals(d)
    start = stamp(first["start_utc"])
    assert m.cash_cost(start, start+timedelta(hours=1)) is None
    assert m.total("grid_import_wh", start, start+timedelta(minutes=15)) is None


@pytest.mark.parametrize("bad", ["overlap", "negative", "naive", "power", "duplicate-soc", "bool-schema"])
def test_invalid_actual_measurements_fail_closed(bad):
    d = measured()
    if bad == "overlap":
        d["energy"].append(copy.deepcopy(d["energy"][0]))
    elif bad == "negative":
        d["energy"][0]["grid_import_wh"] = -1
    elif bad == "naive":
        d["energy"][0]["start_utc"] = "2026-10-31T13:00:00"
    elif bad == "power":
        d["energy_kind"] = "power_w_samples"
    elif bad == "duplicate-soc":
        d["soc"].append(d["soc"][0])
    else:
        d["schema_version"] = True
    with pytest.raises(ActualsError):
        actuals(d)


def test_measured_zero_and_negative_final_prices_are_valid():
    d = measured()
    for row in d["tariffs"]:
        row["retail_eur_kwh"] = -.1
    m = actuals(d)
    p, c = prediction(None)
    r = analyze(p, c, m)
    assert r["actual_grid_cash_cost_eur"] == pytest.approx(-.1)
    assert r["rows"][0]["metrics"]["pv_wh"]["actual"] == 0


def test_soc_has_original_source_time_no_interpolation_or_future_backfill():
    d = measured()
    d["soc"] = [{"at_utc": "2026-10-31T12:59:30+00:00", "percent": 41}]
    m = actuals(d)
    value, source = m.soc_at(stamp("2026-10-31T13:00:00+00:00"))
    assert value == 41 and source["age_seconds"] == 30
    assert m.soc_at(stamp("2026-10-31T13:01:00+00:00")) == (None, None)
    assert m.soc_at(stamp("2026-10-31T12:59:00+00:00")) == (None, None)


@pytest.mark.parametrize("start", [datetime(2026, 3, 29, 0, tzinfo=UTC), datetime(2026, 10, 25, 0, tzinfo=UTC)])
def test_actual_intervals_are_continuous_across_dst(start):
    m = actuals(measured(start=start, count=16))
    assert m.total("load_wh", start, start+timedelta(hours=4)) == 4000


def test_mismatched_plan_and_private_origin_fields_are_not_exposed():
    d = measured()
    d["origin"]["token"] = "PRIVATE-TOKEN-IP-192.168.0.1"
    p, c = prediction(None)
    good = analyze(p, c, actuals(d))
    assert "PRIVATE" not in json.dumps(good) and "192.168" not in json.dumps(good)
    c["input_sha256"] = "wrong"
    bad = analyze(p, c, actuals(d))
    assert bad["status"] == "not_calculable" and bad["realized_savings_eur"] is None


def test_future_forecast_cannot_be_declared_as_completed_measured_energy():
    with pytest.raises(ActualsError, match="Future"):
        actuals(measured(start=datetime.now(UTC)+timedelta(days=1)))

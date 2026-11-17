"""Phase 2: shared physics, independent regulators/limit control/ideal bound."""

import hashlib
import math
import sys
from dataclasses import asdict, replace
from pathlib import Path

from .battery import SOURCES, Battery
from .capabilities import CONFIRMED, EXPANSIONS, MODELS
from .config import SimulationError
from .engine import grid_charge_budget
from .ideal import optimize
from .inputs import digest, validate
from .pv import generate


def account(row, extra, curtail, direct_base, direct_extra, batteries, hours):
    states = [b.finish(hours) for b in batteries]
    pv_charge = sum(s["charge_pv_wh"] for s in states)
    grid_charge = sum(s["charge_grid_wh"] for s in states)
    discharge = sum(s["discharge_wh"] for s in states)
    net = row["base_pv_wh"] + extra - curtail - pv_charge + discharge - row["load_wh"] - grid_charge
    imported, exported = max(0, -net), max(0, net)
    losses = sum(s["losses_wh"] for s in states)
    balance = (row["base_pv_wh"] + extra + imported + sum(s["start_wh"] for s in states)
               - row["load_wh"] - exported - curtail - losses - sum(s["end_wh"] for s in states))
    if abs(balance) > 1e-6:
        raise SimulationError("Phase 2 site balance failed")
    supplied = min(discharge, max(0, row["load_wh"] - direct_base - direct_extra))
    fraction = supplied / discharge if discharge > 1e-10 else 0
    pv_output = sum(s["output_by_source_wh"]["base_pv"] + s["output_by_source_wh"]["extra_pv"]
                    for s in states) * fraction
    extra_output = sum(s["output_by_source_wh"]["extra_pv"] for s in states) * fraction
    return {"grid_import_wh": imported, "grid_export_wh": exported, "losses_wh": losses,
            "maxxi_ac_output_wh": extra - curtail - (states[1]["charge_pv_wh"] if len(states) > 1 else 0)
            + (states[1]["discharge_wh"] if len(states) > 1 else 0),
            "curtailed_wh": curtail, "pv_to_load_wh": direct_base + direct_extra + pv_output,
            "extra_pv_to_load_wh": direct_extra + extra_output,
            "battery_export_wh": discharge - supplied, "battery_transfer_wh": 0.0,
            "balance_error_wh": balance, "e3dc": states[0],
            "maxxi": states[1] if len(states) > 1 else None}


def limits(index, rows, maxxi, config, model):
    ceiling = min(maxxi.config.max_discharge_w, config.operation.maxxi_ac_output_limit_w) if maxxi else 0
    hold = False
    if model == "coordinated" and maxxi and config.operation.price_hold_enabled:
        horizon = rows[index]["at"].timestamp() + config.lookahead_hours * 3600
        peak = max(r["import_eur_kwh"] for r in rows[index:]
                   if r["at"].timestamp() < horizon)
        hold = rows[index]["import_eur_kwh"] + config.min_spread_eur_kwh < peak
        if hold:
            ceiling = 0
    return {"discharge_limit_w": ceiling, "min_soc_percent": maxxi.config.min_soc_percent if maxxi else 0,
            "max_soc_percent": maxxi.config.max_soc_percent if maxxi else 0,
            "charge_limit_w": maxxi.config.max_pv_charge_w if maxxi else 0,
            "price_hold": hold, "exact_discharge_setpoint": None,
            "e3dc_coordination_enabled": model == "coordinated" and config.operation.e3dc_coordination_enabled}


def regulated_interval(index, rows, extra, extras, e3dc, maxxi, config, model, previous,
                       *, grid_optional=False):
    original = rows[index]
    steps = original["interval_seconds"] // config.operation.substep_seconds
    seconds, hours = config.operation.substep_seconds, config.operation.substep_seconds / 3600
    cap = limits(index, rows, maxxi, config, model)
    output = []
    for _ in range(steps):
        row = {**original, "load_wh": original["load_wh"] / steps,
               "base_pv_wh": original["base_pv_wh"] / steps}
        own = extra / steps
        for b in (e3dc, maxxi):
            if b:
                b.begin()
        direct_base = min(row["base_pv_wh"], row["load_wh"])
        residual = row["load_wh"] - direct_base
        ac = config.operation.maxxi_ac_output_limit_w * hours if maxxi else (
            config.operation.pv_only_ac_limit_w * hours
            if config.operation.pv_only_ac_limit_w is not None else own)
        direct_extra = min(own, residual, ac)
        residual -= direct_extra
        base_charge = e3dc.charge(max(0, row["base_pv_wh"] - direct_base), hours, "base_pv")
        own_charge = maxxi.charge(max(0, own - direct_extra), hours, "extra_pv") if maxxi else 0
        own_export = min(max(0, own - direct_extra - own_charge), max(0, ac - direct_extra))
        curtail = max(0, own - direct_extra - own_charge - own_export)
        grid_budget = grid_charge_budget(index, rows, extras, maxxi, e3dc, config) if grid_optional else 0
        grid_charge = 0
        meter_need = row["load_wh"] - (row["base_pv_wh"] - base_charge) - (own - own_charge - curtail)
        if maxxi and grid_budget > 1e-8 and meter_need >= 0 and own_charge <= 1e-9:
            grid_charge = maxxi.charge(grid_budget, hours, "grid")
        if grid_charge > 1e-9:
            previous[:] = [0.0, 0.0]
        else:
            error_w = meter_need / hours - previous[0] - previous[1]
            e3_limit = e3dc.config.max_discharge_w if base_charge <= 1e-9 else 0
            maxxi_limit = min(cap["discharge_limit_w"], max(0, ac - direct_extra - own_export) / hours) if maxxi else 0
            if maxxi and own_charge > 1e-9:
                maxxi_limit = 0
            if cap["e3dc_coordination_enabled"] and maxxi:
                available = min(maxxi_limit, maxxi.available * maxxi.config.discharge_efficiency / hours)
                e3_limit = min(e3_limit, max(0, meter_need / hours - available))
            e3_request = min(e3_limit, max(0, previous[0] + config.operation.e3dc_feedback_gain * error_w))
            maxxi_request = min(maxxi_limit, max(0, previous[1] + config.operation.maxxi_feedback_gain * error_w))
            e3_output = e3dc.discharge(e3_request * hours, hours) if base_charge <= 1e-9 else 0
            maxxi_output = maxxi.discharge(maxxi_request * hours, hours) if maxxi and own_charge <= 1e-9 else 0
            previous[:] = [e3_output / hours, maxxi_output / hours]
        output.append(account(row, own, curtail, direct_base, direct_extra,
                              [e3dc] + ([maxxi] if maxxi else []), hours))
    result = {key: math.fsum(s[key] for s in output) for key in output[0]
              if key not in ("e3dc", "maxxi")}
    for name in ("e3dc", "maxxi"):
        states = [s[name] for s in output if s[name] is not None]
        if not states:
            result[name] = None
            continue
        state = dict(states[-1])
        state["start_wh"] = states[0]["start_wh"]
        for key in ("charge_pv_wh", "charge_grid_wh", "discharge_wh", "losses_wh", "balance_error_wh"):
            state[key] = math.fsum(s[key] for s in states)
        for key in ("charge_pv", "charge_grid", "discharge"):
            state[key + "_w"] = state[key + "_wh"] / (original["interval_seconds"] / 3600)
        state["output_by_source_wh"] = {key: math.fsum(s["output_by_source_wh"][key] for s in states)
                                        for key in SOURCES}
        result[name] = state
    result["limits"] = cap
    result["substeps"] = steps
    result["substep_seconds"] = seconds
    return result


def ideal_interval(row, extra, e3dc, maxxi, plan):
    h = row["interval_seconds"] / 3600
    for b in (e3dc, maxxi):
        if b:
            b.begin()
    for battery, charge, discharge, source in ((e3dc, "e3_charge", "e3_discharge", "base_pv"),
                                                (maxxi, "m_charge", "m_discharge", "extra_pv")):
        if battery:
            target = plan[charge] if plan[charge] > 1e-6 else 0
            actual = battery.charge(target, h, source)
            if battery is maxxi:
                actual_grid = battery.charge(plan["grid_charge"], h, "grid")
                if abs(actual_grid - plan["grid_charge"]) > 1e-4:
                    raise SimulationError("Ideal grid charge does not replay physically")
            target_discharge = plan[discharge] if plan[discharge] > 1e-6 else 0
            actual_discharge = battery.discharge(target_discharge, h) if target_discharge > 0 else 0
            if abs(actual - target) > 1e-4 or abs(actual_discharge - target_discharge) > 1e-4:
                raise SimulationError("Ideal optimum does not replay in existing battery physics")
    return account(row, extra, plan["curtail"], plan["base_direct"], plan["extra_direct"],
                   [e3dc] + ([maxxi] if maxxi else []), h)


def run_case(rows, panel_energy, e3dc_config, config, expansion, model="autonomous", *, grid_optional=False):
    label, multiplier, blocks = EXPANSIONS[expansion]
    maxxi_config = replace(config.maxxi, capacity_wh=config.maxxi.capacity_wh * blocks) if blocks else None
    e3dc, maxxi = Battery(e3dc_config), Battery(maxxi_config) if maxxi_config else None
    extra_wp = math.fsum(p.wp for p in config.panels) * multiplier
    if blocks and extra_wp > blocks * CONFIRMED["max_south_pv_wp_per_m5_v2plus"] + 1e-6:
        raise SimulationError("PV exceeds 3 kWp per modelled M-5.0 V2+ input unit")
    extras = [sum(v[i] for v in panel_energy.values()) * multiplier for i in range(len(rows))]
    initial_dc = e3dc.energy + (maxxi.energy if maxxi else 0)
    initial_ac = e3dc.available * e3dc.config.discharge_efficiency + (
        maxxi.available * maxxi.config.discharge_efficiency if maxxi else 0)
    plan, solver = optimize(rows, extras, e3dc_config, maxxi_config, config,
                            grid_optional=grid_optional) if model == "ideal" else (None, None)
    previous, intervals = [0.0, 0.0], []
    for i, row in enumerate(rows):
        flow = ideal_interval(row, extras[i], e3dc, maxxi, plan[i]) if plan else regulated_interval(
            i, rows, extras[i], extras, e3dc, maxxi, config, model, previous, grid_optional=grid_optional)
        h = row["interval_seconds"] / 3600
        cost = flow["grid_import_wh"] / 1000 * row["import_eur_kwh"]
        fixed = flow["grid_import_wh"] / 1000 * config.operation.fixed_price_eur_kwh
        revenue = flow["grid_export_wh"] / 1000 * row["export_eur_kwh"]
        wear = (flow["e3dc"]["discharge_wh"] * e3dc_config.wear_eur_per_kwh_output
                + (flow["maxxi"]["discharge_wh"] * maxxi_config.wear_eur_per_kwh_output
                   if maxxi else 0)) / 1000
        intervals.append({**flow, "mode": "SIM", "start_utc": row["start_utc"],
            "end_utc": row["end_utc"], "interval_seconds": row["interval_seconds"],
            "load_wh": row["load_wh"], "pv_wh": row["base_pv_wh"] + extras[i],
            "extra_pv_wh": extras[i], "grid_import_w": flow["grid_import_wh"] / h,
            "maxxi_ac_output_w": flow["maxxi_ac_output_wh"] / h,
            "grid_export_w": flow["grid_export_wh"] / h,
            "pv_suedhuette_w": panel_energy["suedhuette"][i] * multiplier / h,
            "pv_suedzaun_w": panel_energy["suedzaun"][i] * multiplier / h,
            "grid_cost_eur": cost, "fixed_grid_cost_eur": fixed,
            "feed_in_revenue_eur": revenue, "wear_eur": wear,
            "net_electricity_cost_eur": cost - revenue,
            "fixed_net_electricity_cost_eur": fixed - revenue,
            "operating_cost_eur": cost - revenue + wear})
    keys = ("load_wh", "pv_wh", "extra_pv_wh", "grid_import_wh", "grid_export_wh", "losses_wh",
            "curtailed_wh", "pv_to_load_wh", "extra_pv_to_load_wh", "battery_export_wh",
            "grid_cost_eur", "fixed_grid_cost_eur", "feed_in_revenue_eur", "wear_eur", "operating_cost_eur",
            "net_electricity_cost_eur", "fixed_net_electricity_cost_eur")
    sums = {key: math.fsum(r[key] for r in intervals) for key in keys}
    final_dc = e3dc.energy + (maxxi.energy if maxxi else 0)
    final_ac = e3dc.available * e3dc.config.discharge_efficiency + (
        maxxi.available * maxxi.config.discharge_efficiency if maxxi else 0)
    balance = (sums["pv_wh"] + sums["grid_import_wh"] + initial_dc - sums["load_wh"]
               - sums["grid_export_wh"] - sums["curtailed_wh"] - sums["losses_wh"] - final_dc)
    if abs(balance) > 1e-5:
        raise SimulationError("Phase 2 cumulative balance failed")
    identity = expansion if not blocks else expansion + "__" + model
    if grid_optional:
        identity += "__grid_optional"
    sums.update(initial_internal_wh=initial_dc, final_internal_wh=final_dc,
        initial_usable_ac_wh=initial_ac, final_usable_ac_wh=final_ac,
        inventory_adjusted_cost_eur=sums["operating_cost_eur"] -
        (final_ac - initial_ac) / 1000 * config.terminal_value_eur_kwh_ac,
        e3dc_soc_end_percent=e3dc.soc, maxxi_soc_end_percent=maxxi.soc if maxxi else None,
        balance_error_wh=balance, annualized_savings_eur=None, payback_years=None)
    return {"id": identity, "expansion": expansion, "operating_model": model,
            "model_label": MODELS[model], "mode": "SIM", "label": label + (
                " · " + MODELS[model] if blocks else "") + (" · optionale Netzladung" if grid_optional else ""),
            "grid_charging_optional_assumption": grid_optional,
            "real_hardware_control_verified": False, "solver": solver,
            "e3dc_config": asdict(e3dc_config), "maxxi_config": asdict(maxxi_config) if maxxi else None,
            "maxxi_input_units_assumed": blocks, "extra_pv_wp": extra_wp,
            "rows": intervals, "summary": sums}


def investment(expansion, config):
    if expansion in config.investments_eur:
        return config.investments_eur[expansion]
    op = config.operation
    if expansion == "e3dc":
        return 0
    if expansion == "pv2_bat5":
        return op.poc_investment_eur
    if expansion == "pv2_only":
        return op.pv_only_2kwp_investment_eur
    if expansion == "pv3_bat5":
        return op.poc_investment_eur + op.additional_3kwp_cost_eur if op.additional_3kwp_cost_eur is not None else None
    if expansion == "pv3_only":
        return op.pv_only_2kwp_investment_eur + op.additional_3kwp_cost_eur if (
            op.pv_only_2kwp_investment_eur is not None and op.additional_3kwp_cost_eur is not None) else None
    return None


def compare(data, config):
    rows, e3dc = validate(data)
    if (sum(p.wp for p in config.panels) != 2000 or config.maxxi.capacity_wh != 5000
            or e3dc.capacity_wh != 13000):
        raise SimulationError("Named expansions require 2 kWp reference PV, 5 kWh blocks and 13 kWh E3/DC")
    if data["data_kind"] == "measured" and data.get("historical_audit", {}).get("status") not in ("passed", "warnings"):
        raise SimulationError("Measured Phase 2 comparison requires an audited historical import")
    if len(rows) > 744:
        raise SimulationError("Phase 2 review horizon is limited to 744 original intervals")
    panels, pv_metadata = generate(rows, data["pv_source"], config)
    cases = {}
    for expansion, (_, _, blocks) in EXPANSIONS.items():
        for model in MODELS if blocks else ("autonomous",):
            case = run_case(rows, panels, e3dc, config, expansion, model)
            cases[case["id"]] = case
            if blocks and config.operation.optional_grid_charging:
                optional = run_case(rows, panels, e3dc, config, expansion, model, grid_optional=True)
                cases[optional["id"]] = optional
    baseline = cases["e3dc"]
    # Isolate the storage increment from the ideal E3/DC dispatch improvement.
    matched_pv = {expansion: run_case(rows, panels, e3dc, config, expansion, "ideal")
                  for expansion in ("pv2_only", "pv3_only", "pv6_only")}
    for case in cases.values():
        summary, base = case["summary"], baseline["summary"]
        summary["savings_cash_eur"] = base["operating_cost_eur"] - summary["operating_cost_eur"]
        summary["savings_inventory_adjusted_eur"] = base["inventory_adjusted_cost_eur"] - summary["inventory_adjusted_cost_eur"]
        summary["additional_self_consumption_wh"] = summary["pv_to_load_wh"] - base["pv_to_load_wh"]
        summary["storage_increment_eur"] = None
        if case["maxxi_config"]:
            peer = case["expansion"].replace("_bat5", "_only").replace("_bat10", "_only")
            reference = matched_pv[peer] if case["operating_model"] == "ideal" else cases[peer]
            summary["storage_increment_eur"] = reference["summary"]["operating_cost_eur"] - summary["operating_cost_eur"]
            summary["storage_increment_inventory_adjusted_eur"] = (
                reference["summary"]["inventory_adjusted_cost_eur"] - summary["inventory_adjusted_cost_eur"])
            case["storage_reference"] = {"expansion": peer, "model": reference["operating_model"],
                                          "summary": reference["summary"]}
        summary["investment_eur"] = investment(case["expansion"], config)
        summary["investment_base_eur"] = (config.operation.poc_investment_eur
            if case["expansion"] in ("pv2_bat5", "pv3_bat5")
            else config.operation.pv_only_2kwp_investment_eur
            if case["expansion"] in ("pv2_only", "pv3_only") else None)
        summary["investment_additional_3kwp_eur"] = (config.operation.additional_3kwp_cost_eur
            if case["expansion"].startswith("pv3_") else 0)
        cumulative = 0
        for current, original in zip(case["rows"], baseline["rows"]):
            cumulative += original["operating_cost_eur"] - current["operating_cost_eur"]
            current["cumulative_savings_cash_eur"] = cumulative
    code = Path(__file__).parent
    code_hash = digest({p.name: hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                        for p in sorted(code.glob("*.py"))})
    return {"simulation_schema": 2, "mode": "SIM", "engine": "maxxicharge-phase2-1",
            "run_id": digest({"input": digest(data), "config": asdict(config), "code": code_hash}),
            "engine_code_sha256": code_hash, "python_version": ".".join(map(str, sys.version_info[:3])),
            "devices_commanded": False, "hardware_transport_available": False,
            "data_kind": data["data_kind"], "source_sha256": data["source_sha256"],
            "input_sha256": digest(data), "config_sha256": digest(asdict(config)),
            "start_utc": rows[0]["start_utc"], "end_utc": rows[-1]["end_utc"],
            "coverage_hours": sum(r["interval_seconds"] for r in rows) / 3600,
            "pv_model": pv_metadata, "config": asdict(config), "scenarios": cases,
            "manufacturer_capabilities": CONFIRMED,
            "historical_audit": data.get("historical_audit"),
            **({"measurement_preparation": data["measurement_preparation"]}
               if "measurement_preparation" in data else {}),
            "assumptions": [
                "SIM: keine realen Gerätebefehle; neue PV-Erträge sind modelliert.",
                "A/B: interne Rückkopplungsregler und Reaktionszeiten sind Annahmen, keine Firmware-Nachbildung.",
                "B: EMS setzt Grenzen, keine exakten Entladeleistungs-Sollwerte; E3/DC-Koordination separat konfiguriert.",
                "C: perfekte Kenntnis der Reihe und freie Steuerung, nur theoretische Vergleichsobergrenze.",
                "Gemeinsames Maxxi-AC-Limit für direkte PV und Batterie; AC-/MPPT-Topologie ist unbestätigt.",
                "Stundenwerte innerhalb eines Intervalls konstant; Teilintervalle sind SIM, keine Messungen.",
                "Keine E3/DC-AC-Aufnahme fremder Batterieenergie modelliert; reale Transferfreiheit in A/B unbewiesen.",
                "Eine 6-kWp-Variante benötigt zwei geeignete PV-Eingangsgeräte; Zahl und AC-Topologie bleiben Annahmen.",
                "Preisoptimierte Netzladung nur als explizite Zusatzvariante mit unbestätigter externer Start/Stopp-Fähigkeit.",
                "Speichermehrwert umfasst die ausgewiesenen System-/Wechselrichtergrenzen gegenüber gleicher PV-Leistung.",
                "Keine belastbare Jahresamortisation aus fünf Novembertagen.",
            ]}

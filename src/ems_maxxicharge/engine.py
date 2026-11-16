"""Deterministic counterfactual coordination, not a production controller."""

import hashlib
import sys
from dataclasses import asdict
from pathlib import Path

from . import VERSION
from .battery import Battery
from .config import SCENARIOS, SimulationError
from .inputs import digest, validate
from .pv import generate


def grid_charge_budget(index, rows, extras, maxxi, e3dc, config):
    """Bounded spread heuristic with useful demand and PV headroom reservation.

    Perfect knowledge of the supplied forecast/historical window is assumed.
    This is deliberately reported as a heuristic, not a global optimum.
    """
    if not maxxi or not config.grid_charging_enabled:
        return 0.0
    bat = maxxi.config
    now = rows[index]
    if now["base_pv_wh"] + extras[index] > now["load_wh"]:
        return 0.0
    roundtrip = bat.charge_efficiency * bat.discharge_efficiency
    threshold = (now["import_eur_kwh"] / roundtrip
                 + bat.wear_eur_per_kwh_output + config.min_spread_eur_kwh)
    useful_ac, pv_reserve_dc, elapsed = 0.0, 0.0, 0.0
    for j in range(index + 1, len(rows)):
        future = rows[j]
        elapsed += future["interval_seconds"] / 3600
        if elapsed > config.lookahead_hours:
            break
        # A future cheaper/equal opportunity should supply its own following window.
        if future["import_eur_kwh"] < now["import_eur_kwh"]:
            break
        deficit = max(0, future["load_wh"] - future["base_pv_wh"] - extras[j])
        if future["import_eur_kwh"] > threshold:
            useful_ac += min(deficit, bat.max_discharge_w * future["interval_seconds"] / 3600)
        own_surplus = min(extras[j], max(0, extras[j] + future["base_pv_wh"]
                                         - future["load_wh"]))
        pv_reserve_dc += min(own_surplus, bat.max_pv_charge_w
                             * future["interval_seconds"] / 3600) * bat.charge_efficiency
    # Existing usable E3/DC energy can already cover demand. Do not buy it twice.
    useful_ac = max(0, useful_ac - e3dc.available * e3dc.config.discharge_efficiency)
    needed_dc = max(0, useful_ac / bat.discharge_efficiency - maxxi.available - pv_reserve_dc)
    headroom = max(0, maxxi.maximum - maxxi.energy - pv_reserve_dc)
    return min(needed_dc, headroom) / bat.charge_efficiency


def scenario(rows, e3dc_config, panel_energy, config, scenario_id):
    label, multiplier = SCENARIOS[scenario_id]
    e3dc = Battery(e3dc_config)
    maxxi_config = config.battery(scenario_id)
    maxxi = Battery(maxxi_config) if maxxi_config else None
    batteries = [e3dc] + ([maxxi] if maxxi else [])
    initial_usable_ac = sum(b.available * b.config.discharge_efficiency for b in batteries)
    initial_internal = sum(b.energy for b in batteries)
    extras = [sum(v[i] for v in panel_energy.values()) * multiplier for i in range(len(rows))]
    result = []
    sums = dict.fromkeys(("load_wh", "pv_wh", "extra_pv_wh", "grid_import_wh", "grid_export_wh",
                          "losses_wh", "pv_to_load_wh", "extra_pv_to_load_wh", "grid_cost_eur",
                          "feed_in_revenue_eur", "wear_eur", "operating_cost_eur"), 0.0)
    for i, row in enumerate(rows):
        hours = row["interval_seconds"] / 3600
        for battery in batteries:
            battery.begin()
        load, own, base = row["load_wh"], extras[i], row["base_pv_wh"]
        # Existing PV serves the house, leaving own extra PV for Maxxi first.
        # Neither battery may charge from the other battery's output.
        base_direct = min(base, load)
        load -= base_direct
        base -= base_direct
        own_direct = min(own, load)
        load -= own_direct
        own -= own_direct
        if maxxi and own > 0:
            own -= maxxi.charge(own, hours, "extra_pv")
        if base > 0:
            base -= e3dc.charge(base, hours, "base_pv")
        grid_charge = grid_charge_budget(i, rows, extras, maxxi, e3dc, config)
        if maxxi and grid_charge > 1e-9 and own + base < 1e-9:
            grid_charge = maxxi.charge(grid_charge, hours, "grid")
        else:
            grid_charge = 0.0
        # Every discharge is capped by residual HOUSE demand. No battery output
        # can feed another battery's charger, even during planned grid charging.
        if grid_charge <= 1e-9:
            if maxxi and maxxi.flow["charge_pv_wh"] <= 1e-9:
                load -= maxxi.discharge(load, hours)
            if e3dc.flow["charge_pv_wh"] <= 1e-9:
                load -= e3dc.discharge(max(0, load), hours)
        flow = {"e3dc": e3dc.finish(hours), "maxxi": maxxi.finish(hours) if maxxi else None}
        grid_import, grid_export = max(0, load) + grid_charge, base + own
        losses = sum(b.flow["losses_wh"] for b in batteries)
        pv_output = sum(b.flow["output_by_source_wh"]["base_pv"]
                        + b.flow["output_by_source_wh"]["extra_pv"] for b in batteries)
        extra_output = sum(b.flow["output_by_source_wh"]["extra_pv"] for b in batteries)
        grid_cost = grid_import / 1000 * row["import_eur_kwh"]
        revenue = grid_export / 1000 * row["export_eur_kwh"]
        wear = sum(b.flow["discharge_wh"] / 1000 * b.config.wear_eur_per_kwh_output
                   for b in batteries)
        end_internal = sum(b.energy for b in batteries)
        start_internal = sum(b.flow["start_wh"] for b in batteries)
        pv_total = row["base_pv_wh"] + extras[i]
        balance = (pv_total + grid_import + start_internal - row["load_wh"]
                   - grid_export - end_internal - losses)
        if abs(balance) > 1e-6 or min(grid_import, grid_export) > 1e-6:
            raise SimulationError("Site energy conservation or exclusive grid direction failed")
        interval = {
            "mode": "SIM", "start_utc": row["start_utc"], "end_utc": row["end_utc"],
            "interval_seconds": row["interval_seconds"], "load_wh": row["load_wh"],
            "pv_wh": pv_total, "extra_pv_wh": extras[i],
            "pv_suedhuette_w": panel_energy["suedhuette"][i] * multiplier / hours,
            "pv_suedzaun_w": panel_energy["suedzaun"][i] * multiplier / hours,
            "grid_import_wh": grid_import, "grid_export_wh": grid_export,
            "grid_import_w": grid_import / hours, "grid_export_w": grid_export / hours,
            "import_eur_kwh": row["import_eur_kwh"], "export_eur_kwh": row["export_eur_kwh"],
            "losses_wh": losses, "pv_to_load_wh": own_direct + base_direct + pv_output,
            "extra_pv_to_load_wh": own_direct + extra_output,
            "grid_cost_eur": grid_cost, "feed_in_revenue_eur": revenue,
            "wear_eur": wear, "operating_cost_eur": grid_cost - revenue + wear,
            "battery_transfer_wh": 0.0, "balance_error_wh": balance, **flow,
        }
        for key in sums:
            sums[key] += interval[key]
        interval["cumulative_operating_cost_eur"] = sums["operating_cost_eur"]
        result.append(interval)
    final_usable_ac = sum(b.available * b.config.discharge_efficiency for b in batteries)
    value = (final_usable_ac - initial_usable_ac) / 1000 * config.terminal_value_eur_kwh_ac
    cumulative_balance = (sums["pv_wh"] + sums["grid_import_wh"] + initial_internal
                          - sums["load_wh"] - sums["grid_export_wh"] - sums["losses_wh"]
                          - sum(b.energy for b in batteries))
    if abs(cumulative_balance) > 1e-5:
        raise SimulationError("Cumulative energy balance failed")
    return {
        "id": scenario_id, "label": label, "mode": "SIM", "rows": result,
        "pv_multiplier": multiplier, "e3dc_config": asdict(e3dc_config),
        "maxxi_config": asdict(maxxi_config) if maxxi_config else None,
        "summary": {**sums, "initial_internal_wh": initial_internal,
                    "final_internal_wh": sum(b.energy for b in batteries),
                    "initial_usable_ac_wh": initial_usable_ac,
                    "final_usable_ac_wh": final_usable_ac,
                    "inventory_change_value_eur": value,
                    "inventory_adjusted_cost_eur": sums["operating_cost_eur"] - value,
                    "investment_eur": config.investments_eur.get(scenario_id),
                    "annual_maintenance_eur": config.annual_maintenance_eur.get(scenario_id),
                    "annualized_savings_eur": None, "payback_years": None,
                    "balance_error_wh": cumulative_balance},
    }


def simulate(data, config):
    rows, e3dc = validate(data)
    coverage_hours = sum(r["interval_seconds"] for r in rows) / 3600
    if config.representative_year_confirmed and (
            data["data_kind"] != "measured" or coverage_hours < 8760):
        raise SimulationError("Annual economics requires a confirmed representative measured year")
    panel_energy, pv_metadata = generate(rows, data["pv_source"], config)
    scenarios = {key: scenario(rows, e3dc, panel_energy, config, key) for key in SCENARIOS}
    baseline = scenarios["e3dc"]
    for result in scenarios.values():
        sums, base = result["summary"], baseline["summary"]
        sums["savings_cash_eur"] = base["operating_cost_eur"] - sums["operating_cost_eur"]
        sums["savings_inventory_adjusted_eur"] = (base["inventory_adjusted_cost_eur"]
                                                   - sums["inventory_adjusted_cost_eur"])
        sums["additional_self_consumption_wh"] = sums["pv_to_load_wh"] - base["pv_to_load_wh"]
        sums["grid_import_reduction_wh"] = base["grid_import_wh"] - sums["grid_import_wh"]
        investment = sums["investment_eur"]
        sums["horizon_savings_minus_investment_eur"] = (
            sums["savings_cash_eur"] - investment if investment is not None else None)
        if config.representative_year_confirmed:
            maintenance = sums["annual_maintenance_eur"]
            if maintenance is not None:
                annual = sums["savings_inventory_adjusted_eur"] * 8760 / coverage_hours - maintenance
                sums["annualized_savings_eur"] = annual
                sums["payback_years"] = investment / annual if (
                    investment is not None and annual > 0) else None
        cumulative = 0.0
        for current, reference in zip(result["rows"], baseline["rows"]):
            cumulative += reference["operating_cost_eur"] - current["operating_cost_eur"]
            current["cumulative_savings_cash_eur"] = cumulative
    code = Path(__file__).parent
    source_hash = digest({p.name: hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                          for p in sorted(code.glob("*.py"))})
    run_id = digest({"input": digest(data), "config": digest(asdict(config)), "code": source_hash})
    return {
        "simulation_schema": 1, "mode": "SIM", "engine": VERSION,
        "run_id": run_id, "engine_code_sha256": source_hash,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "devices_commanded": False, "hardware_transport_available": False,
        "data_kind": data["data_kind"], "source_sha256": data["source_sha256"],
        "input_sha256": digest(data), "config_sha256": digest(asdict(config)),
        "scope_evidence": data.get("scope_evidence", "declared input contract"),
        "pv_conversion_factor_to_ac_equivalent": data.get("pv_conversion_factor_to_ac_equivalent"),
        "start_utc": rows[0]["start_utc"], "end_utc": rows[-1]["end_utc"],
        "coverage_hours": coverage_hours,
        "pv_model": pv_metadata, "config": asdict(config), "scenarios": scenarios,
        "assumptions": [
            "SIM counterfactuals, not measured savings or native EOS controller replays",
            data.get("scope_evidence", "Input scope per supplied contract, source confirmation external"),
            "E3/DC reference: configured constant-efficiency self-consumption model",
            "AC-equivalent site bus; 800 W limit applies to additional battery discharge",
            "PV AC conversion/inverter clipping is not a validated MaxxiCharge hardware model",
            "6 kWp uses three times each 1 kWp panel profile, same geometry",
            "Grid charging: finite-lookahead spread heuristic, no optimality claim",
            "92% charge/discharge efficiencies and unconfirmed charge limits are assumptions",
            "No simultaneous site import/export, battery charge/discharge or battery transfer",
            "PV self-consumption means energy delivered to load, excludes storage losses",
            "Terminal inventory values usable AC energy at the same configured EUR/kWh",
            "No annualization or payback from short/nonrepresentative historical windows",
        ],
    }

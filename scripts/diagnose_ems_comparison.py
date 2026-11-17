"""Final read-only diagnostics of stored results, not a new controller or calibration.

Only explicitly labelled offline reference experiments use the existing engine.
Original observations, the thirteen scenarios and their configurations stay frozen.
"""

import argparse
import csv
import hashlib
import io
import math
from dataclasses import asdict, replace
from pathlib import Path
from zoneinfo import ZoneInfo

from ems_maxxicharge.comparison import run_case
from ems_maxxicharge.config import Config
from ems_maxxicharge.inputs import canonical, digest, read_json, stamp, validate
from ems_maxxicharge.pv import generate
from eos_pv_helper.dashboard_view import validate_sim_report
from eos_pv_helper.energy_data import verify_prepared


def identity(row):
    return stamp(row["start_utc"]), stamp(row["end_utc"])


def baseline_diagnosis(measured, model, inputs, original_rows, battery):
    collections = (measured, model, inputs, original_rows)
    if not measured or any(len(rows) != len(measured) for rows in collections):
        raise ValueError("Diagnostic coverage differs")
    if any(len({identity(r) for r in rows}) != len(rows) for rows in collections):
        raise ValueError("Duplicate diagnostic interval")
    rows = []
    internal = battery["capacity_wh"] * battery["initial_soc_percent"] / 100
    implied_states = [internal]
    for m, s, source, original in zip(*collections):
        if any(identity(r) != identity(m) for r in (s, source, original)):
            raise ValueError("Diagnostic timestamps must match exactly; no fitted shifts")
        price, effective = source["import_eur_kwh"], m["import_eur_kwh"]
        c = s["e3dc"]["charge_pv_wh"] + s["e3dc"]["charge_grid_wh"]
        d = s["e3dc"]["discharge_wh"]
        source_residual = (
            m["base_pv_wh"]
            + m["grid_import_wh"]
            + m["battery_discharge_wh"]
            - m["grid_export_wh"]
            - m["battery_charge_wh"]
            - m["load_wh"]
        )
        model_residual = (
            s["pv_wh"] + s["grid_import_wh"] + d - s["grid_export_wh"] - c - s["load_wh"]
        )
        flow_deltas = {
            "load": s["load_wh"] - m["load_wh"],
            "pv": -(s["pv_wh"] - m["base_pv_wh"]),
            "export": s["grid_export_wh"] - m["grid_export_wh"],
            "battery_charge": c - m["battery_charge_wh"],
            "battery_discharge": -(d - m["battery_discharge_wh"]),
            "meter_balance": model_residual - source_residual,
        }
        attribution = {
            key + "_cost_eur": value / 1000 * effective for key, value in flow_deltas.items()
        }
        tariff = s["grid_import_wh"] / 1000 * (price - effective)
        cost_delta = s["grid_cost_eur"] - m["grid_cost_eur"]
        cost_identity_residual = cost_delta - tariff - math.fsum(attribution.values())
        if abs(cost_identity_residual) > 1e-8:
            raise ValueError("Hourly diagnostic cost identity failed")
        raw_mean = original.get("tariff_hourly_mean_raw")
        raw_mean = float(raw_mean) if raw_mean not in (None, "") else None
        if raw_mean is not None and not math.isfinite(raw_mean):
            raise ValueError("Nonfinite alternative tariff")
        internal += (
            m["battery_charge_wh"] * battery["charge_efficiency"]
            - m["battery_discharge_wh"] / battery["discharge_efficiency"]
        )
        implied_states.append(internal)
        row = {
            "start_utc": source["start_utc"],
            "end_utc": source["end_utc"],
            "start_berlin": stamp(source["start_utc"])
            .astimezone(ZoneInfo("Europe/Berlin"))
            .isoformat(),
            "measured_load_wh": m["load_wh"],
            "model_load_wh": s["load_wh"],
            "measured_pv_wh": m["base_pv_wh"],
            "model_pv_wh": s["pv_wh"],
            "measured_import_wh": m["grid_import_wh"],
            "model_import_wh": s["grid_import_wh"],
            "measured_export_wh": m["grid_export_wh"],
            "model_export_wh": s["grid_export_wh"],
            "measured_battery_charge_wh": m["battery_charge_wh"],
            "model_battery_charge_wh": c,
            "measured_battery_discharge_wh": m["battery_discharge_wh"],
            "model_battery_discharge_wh": d,
            "model_battery_loss_wh": s["e3dc"]["losses_wh"],
            "measured_balance_error_wh": source_residual,
            "model_balance_error_wh": model_residual,
            "effective_retail_eur_kwh": effective,
            "model_retail_eur_kwh": price,
            "alternative_raw_mean_eur_kwh": raw_mean,
            "measured_import_cost_eur": m["grid_cost_eur"],
            "model_import_cost_eur": s["grid_cost_eur"],
            "cost_delta_eur": cost_delta,
            "tariff_cost_eur": tariff,
            **attribution,
            "unexplained_cost_identity_residual_eur": cost_identity_residual,
            "measured_repriced_raw_mean_delta_eur": (
                m["grid_import_wh"] / 1000 * raw_mean - m["grid_cost_eur"]
                if raw_mean is not None
                else None
            ),
            "model_repriced_raw_mean_delta_eur": (
                s["grid_import_wh"] / 1000 * (raw_mean - price) if raw_mean is not None else None
            ),
            "valid_soc_start_percent": m.get("soc_start_percent"),
            "valid_soc_end_percent": m.get("soc_end_percent"),
            "original_reported_soc_end_percent": float(original["soc_end_percent"])
            if original.get("soc_end_percent")
            else None,
            "soc_end_observed_at_utc": m.get("soc_end_at_utc"),
            "soc_end_age_seconds": m.get("soc_end_age_seconds"),
            "model_soc_start_percent": s["e3dc"]["start_wh"] / battery["capacity_wh"] * 100,
            "model_soc_end_percent": s["e3dc"]["soc_percent"],
            "counter_implied_internal_wh_at_assumed_efficiency": internal,
        }
        rows.append(row)
    total_keys = [k for k, v in rows[0].items() if k.endswith(("_cost_eur", "_cost_wh"))]
    total_keys += [
        "cost_delta_eur",
        "measured_import_cost_eur",
        "model_import_cost_eur",
        "unexplained_cost_identity_residual_eur",
        "measured_repriced_raw_mean_delta_eur",
        "model_repriced_raw_mean_delta_eur",
    ]
    total_keys += [k for k in rows[0] if k.endswith("_wh") and not k.startswith("counter_implied")]
    totals = {
        k: math.fsum(r[k] for r in rows) if all(r[k] is not None for r in rows) else None
        for k in sorted(set(total_keys))
    }
    observed_kwh = totals["measured_import_wh"] / 1000
    average = totals["measured_import_cost_eur"] / observed_kwh if observed_kwh else 0
    amount = (totals["model_import_wh"] - totals["measured_import_wh"]) / 1000 * average
    timing = math.fsum(
        (r["model_import_wh"] - r["measured_import_wh"])
        / 1000
        * (r["effective_retail_eur_kwh"] - average)
        for r in rows
    )
    night = [
        m
        for m in measured
        if m["base_pv_wh"] == 0 and m["grid_import_wh"] > 0 and m["battery_charge_wh"] > 0
    ]
    return {
        "status": "provisional",
        "historical_acceptance_passed": False,
        "attribution_kind": "accounting_identity_not_independent_causal_estimates",
        "interval_identity_match": True,
        "rows": rows,
        "totals": totals,
        "volume_vs_timing": {
            "measured_average_import_eur_kwh": average,
            "quantity_at_observed_average_cost_eur": amount,
            "hourly_distribution_effect_eur": timing,
            "alternative_tariff_gap_change_eur": (
                totals["model_repriced_raw_mean_delta_eur"]
                - totals["measured_repriced_raw_mean_delta_eur"]
                if totals["model_repriced_raw_mean_delta_eur"] is not None
                and totals["measured_repriced_raw_mean_delta_eur"] is not None
                else None
            ),
        },
        "battery_boundary_diagnostic": {
            "initial_internal_wh": implied_states[0],
            "implied_end_internal_wh": implied_states[-1],
            "minimum_implied_internal_wh": min(implied_states),
            "reserve_wh": battery["capacity_wh"] * battery["min_soc_percent"] / 100,
            "charge_efficiency_assumption": battery["charge_efficiency"],
            "discharge_efficiency_assumption": battery["discharge_efficiency"],
            "measured_counter_trajectory_incompatible_with_configured_bounds": (
                min(implied_states)
                < battery["capacity_wh"] * battery["min_soc_percent"] / 100 - 1e-6
                or max(implied_states)
                > battery["capacity_wh"] * battery["max_soc_percent"] / 100 + 1e-6
            ),
            "charge_without_pv_intervals": len(night),
            "charge_without_pv_wh": math.fsum(m["battery_charge_wh"] for m in night),
            "owner_of_historical_charging": "not_established_by_energy_export",
            "parameters_fitted_or_applied": False,
            "initial_soc_matches_valid_observation": (
                measured[0].get("soc_start_percent") is not None
                and abs(measured[0]["soc_start_percent"] - battery["initial_soc_percent"]) < 1e-8
            ),
        },
    }


def reference_experiments(data, result):
    """Use existing forward model/config knobs only; no changes to stored cases."""
    engine = Path(run_case.__code__.co_filename).parent
    active_hash = digest(
        {
            p.name: hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for p in sorted(engine.glob("*.py"))
        }
    )
    if active_hash != result["engine_code_sha256"]:
        raise ValueError("Stored scenarios and reference engine revision differ")
    config = Config.from_dict(result["config"])
    if config.operation.e3dc_coordination_enabled:
        raise ValueError("A/B no-hold identity requires the recorded uncoordinated E3/DC case")
    rows, e3dc = validate(data)
    panels, _ = generate(rows, data["pv_source"], config)
    no_hold = replace(config, operation=replace(config.operation, price_hold_enabled=False))
    matched = replace(
        config,
        operation=replace(
            config.operation, pv_only_ac_limit_w=config.operation.maxxi_ac_output_limit_w
        ),
    )
    experiments, comparisons = {}, []
    for expansion in ("pv2_bat5", "pv3_bat5", "pv6_bat10"):
        a, b = [
            result["scenarios"][expansion + "__" + model] for model in ("autonomous", "coordinated")
        ]
        disabled = run_case(rows, panels, e3dc, no_hold, expansion, "coordinated")
        numeric = (
            "operating_cost_eur",
            "inventory_adjusted_cost_eur",
            "grid_import_wh",
            "grid_export_wh",
            "losses_wh",
            "curtailed_wh",
        )
        residual = max(abs(disabled["summary"][k] - a["summary"][k]) for k in numeric)
        if residual > 1e-7:
            raise ValueError("No-hold diagnostic does not reproduce A")
        experiments[expansion] = {
            "price_hold_hours": sum(r["limits"]["price_hold"] for r in b["rows"]),
            "no_hold_summary": disabled["summary"],
            "no_hold_config_sha256": digest(asdict(no_hold)),
            "explicit_change": {"price_hold_enabled": False},
            "max_summary_delta_to_A": residual,
            "B_minus_A_cash_cost_eur": b["summary"]["operating_cost_eur"]
            - a["summary"]["operating_cost_eur"],
            "B_minus_A_inventory_cost_eur": b["summary"]["inventory_adjusted_cost_eur"]
            - a["summary"]["inventory_adjusted_cost_eur"],
            "B_minus_A_final_usable_ac_wh": b["summary"]["final_usable_ac_wh"]
            - a["summary"]["final_usable_ac_wh"],
            "B_minus_A_curtailment_wh": b["summary"]["curtailed_wh"] - a["summary"]["curtailed_wh"],
            "B_minus_A_loss_wh": b["summary"]["losses_wh"] - a["summary"]["losses_wh"],
        }
        peer = expansion.replace("_bat5", "_only").replace("_bat10", "_only")
        peers = {
            model: run_case(rows, panels, e3dc, matched, peer, model)
            for model in ("autonomous", "ideal")
        }
        for model in ("autonomous", "coordinated", "ideal"):
            case = result["scenarios"][expansion + "__" + model]
            s = case["summary"]
            reference = case["storage_reference"]["summary"]
            capped = peers["ideal" if model == "ideal" else "autonomous"]["summary"]
            original_pv = result["scenarios"][peer]["summary"]
            total_capex, pv_capex = s["investment_eur"], original_pv["investment_eur"]
            comparisons.append(
                {
                    "expansion": expansion,
                    "model": model,
                    "pv_reference_model": "ideal" if model == "ideal" else "autonomous",
                    "stored_pv_only_ac_limit_w": config.operation.pv_only_ac_limit_w,
                    "matched_pv_only_ac_limit_w": matched.operation.pv_only_ac_limit_w,
                    "pv_only_net_cost_eur": reference["operating_cost_eur"],
                    "pv_with_storage_net_cost_eur": s["operating_cost_eur"],
                    "package_increment_cash_eur": s["storage_increment_eur"],
                    "package_increment_inventory_eur": s[
                        "storage_increment_inventory_adjusted_eur"
                    ],
                    "same_ac_pv_only_net_cost_eur": capped["operating_cost_eur"],
                    "same_ac_pv_only_inventory_cost_eur": capped["inventory_adjusted_cost_eur"],
                    "same_ac_storage_increment_cash_eur": capped["operating_cost_eur"]
                    - s["operating_cost_eur"],
                    "same_ac_storage_increment_inventory_eur": capped["inventory_adjusted_cost_eur"]
                    - s["inventory_adjusted_cost_eur"],
                    "pv_only_investment_eur": pv_capex,
                    "package_investment_eur": total_capex,
                    "storage_capex_premium_eur": total_capex - pv_capex
                    if total_capex is not None and pv_capex is not None
                    else None,
                    "same_ac_storage_capex_premium_eur": None,
                    "capex_basis": "original_package_minus_original_PV_quote; matched_AC_quote_not_established",
                    "annual_savings_eur": None,
                    "payback_years": None,
                }
            )
    return {
        "status": "diagnostic_only",
        "original_config_sha256": result["config_sha256"],
        "same_ac_reference_config_sha256": digest(asdict(matched)),
        "ab": experiments,
        "storage_comparisons": comparisons,
    }


def to_csv(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def markdown(diagnostic, result):
    b, refs = diagnostic["baseline"], diagnostic["experiments"]
    t, split, battery = b["totals"], b["volume_vs_timing"], b["battery_boundary_diagnostic"]

    def n(value, digits=2):
        return "offen" if value is None else f"{value:.{digits}f}".replace(".", ",")

    lines = [
        "# MaxxiCharge-Abschlussdiagnose · VORLÄUFIG",
        "",
        "Messwerte, ursprüngliche 13 Szenarien und deren Parameter bleiben unverändert. Keine Kalibrierung an eine Referenzsumme.",
        "",
        "## Baseline stundenweise",
        "",
        f"Gemessene Bezugskosten {n(t['measured_import_cost_eur'], 5)} EUR, simuliert {n(t['model_import_cost_eur'], 5)} EUR; Differenz {n(t['cost_delta_eur'], 5)} EUR.",
        f"Netzbezug gemessen {n(t['measured_import_wh'] / 1000, 6)} kWh, modelliert {n(t['model_import_wh'] / 1000, 6)} kWh.",
        f"Mengeneffekt zum gemessenen Durchschnittspreis: {n(split['quantity_at_observed_average_cost_eur'], 5)} EUR; Verteilung auf Stundenpreise: {n(split['hourly_distribution_effect_eur'], 5)} EUR.",
        "",
        "Die folgende Zerlegung ist eine buchhalterische Identität. Batterie, SoC, Messgrenzen und Reglerverhalten sind keine unabhängig identifizierten additiven Ursachen.",
        "",
        "| Beitrag zur Kostenabweichung | EUR |",
        "| --- | ---: |",
    ]
    labels = {
        "tariff_cost_eur": "Angewandter Preis gegenüber gemessenem effektivem Stundenpreis",
        "load_cost_eur": "Haus-/Standortlastdifferenz",
        "pv_cost_eur": "PV-Differenz",
        "export_cost_eur": "Anderer Exportfluss",
        "battery_charge_cost_eur": "Andere Batterieladung",
        "battery_discharge_cost_eur": "Andere Batterieentladung",
        "meter_balance_cost_eur": "Messbilanz/zeitliche Restabweichung",
    }
    lines += [f"| {label} | {n(t[key], 5)} |" for key, label in labels.items()]
    lines += [
        "",
        "Angewandter Preis = gemessene Kosten / gemessener Bezug, soweit Bezug vorhanden. Ein Nullbeitrag ist damit ein Konsistenznachweis, keine unabhängige Viertelstunden-Tarifvalidierung.",
        f"Sensitivität mit Exportspalte tariff_hourly_mean_raw: gemessene Energiemengen {n(t['measured_repriced_raw_mean_delta_eur'], 5)} EUR andere Kosten; simulierte Mengen {n(t['model_repriced_raw_mean_delta_eur'], 5)} EUR andere Kosten. Dies ist keine Korrektur und kein bewiesener Fehlerbetrag.",
        f"Die Kostenlücke ändert sich in genau dieser Tarif-Sensitivität um {n(split['alternative_tariff_gap_change_eur'], 5)} EUR; das ist keine allgemeine Fehlerschranke für unbekannte Viertelstundenprofile.",
        "Alle Intervallgrenzen stimmen exakt in UTC überein; Berliner Ortszeit steht zusätzlich im Stunden-CSV. Keine verschobene Reihe wurde passend gemacht. Die zeitliche Zuordnung der ursprünglichen Zähler und Viertelstundenpreise bleibt ohne feinere Originaldaten begrenzt prüfbar.",
        "",
        "## Batterie- und SoC-Grenzen",
        "",
        f"Gemessene Ladung/Entladung: {n(t['measured_battery_charge_wh'] / 1000, 6)} / {n(t['measured_battery_discharge_wh'] / 1000, 6)} kWh; Modell: {n(t['model_battery_charge_wh'] / 1000, 6)} / {n(t['model_battery_discharge_wh'] / 1000, 6)} kWh.",
        f"Ladung bei 0 Wh PV und positivem Bezug: {battery['charge_without_pv_intervals']} Stunden, {n(battery['charge_without_pv_wh'] / 1000, 6)} kWh Ladung. Die Baseline erlaubt keine E3/DC-Netzladung. Der historische Befehls-Owner ist aus den Energiespalten nicht erkennbar.",
        f"Anfangsenergie {n(battery['initial_internal_wh'] / 1000, 3)} kWh. Unter den deklarierten AC-Grenzen und unveränderten Wirkungsgraden ergibt die gemessene Zählerfolge rechnerisch {n(battery['implied_end_internal_wh'] / 1000, 3)} kWh Endenergie; untere Modellreserve {n(battery['reserve_wh'] / 1000, 3)} kWh.",
        "Eine negative oder grenzverletzende rechnerische Energie ist keine Messung des Speicherinhalts. Sie zeigt die Unvereinbarkeit von Zählergrenze, Zeitbasis, Wirkungsgrad-/Kapazitäts-/Reserveannahmen; sie darf nicht durch Parameter-Fitting kaschiert werden. Eine kleine Standort-Bilanzabweichung beweist keine korrekten Einzelmessgrenzen: gemeinsame oder kompensierende Sensorfehler sind damit nicht ausgeschlossen.",
        "Der Anfangs-SoC war frisch und wurde identisch verwendet. Spätere veraltete SoC-Punkte werden nicht als gültige Grenzwerte interpretiert. Ihr Kostenanteil kann nicht unabhängig vom Batterieverhalten beziffert werden. Die unveränderten zwei Stunden über 50 Wh bleiben in der Messbilanz erhalten.",
        "Diese Historienrechnung verwendet dieselben gemessenen Last-/PV-Eingaben. Der Befund ist nicht mit Prognosefehlern eines künftig laufenden EOS-Plans gleichzusetzen.",
        "",
        "## Warum B schlechter als A ist",
        "",
        "B ist derzeit eine Preis-Halteheuristik, kein frei optimierender EMS-Regler. E3/DC-Koordination ist in der gespeicherten Konfiguration deaktiviert. Ein isolierter Vorwärtslauf mit ausschließlich abgeschalteter Halteheuristik reproduziert A für alle drei Ausbauten; Originalergebnisse bleiben eingefroren.",
        "",
        "| Ausbau | B-Haltestunden | B minus A Cash-Kosten EUR | Nach Endwertkorrektur EUR | Mehr Endenergie AC kWh | Mehr Abregelung kWh |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for expansion, r in refs["ab"].items():
        lines.append(
            f"| {expansion} | {r['price_hold_hours']} | {n(r['B_minus_A_cash_cost_eur'], 5)} | {n(r['B_minus_A_inventory_cost_eur'], 5)} | {n(r['B_minus_A_final_usable_ac_wh'] / 1000, 5)} | {n(r['B_minus_A_curtailment_wh'] / 1000, 5)} |"
        )
    lines += [
        "",
        "Die Halteregel reserviert Energie für einen höheren Preis im 24-h-Fenster, ohne deren gesamten zukünftigen Nutzen samt PV-Nachladung und Endhorizont zu optimieren. Ein Teil des Nachteils steckt in zusätzlicher Endenergie; nach identischer Endwertbewertung bleibt der ausgewiesene Rest. Das ist ein Befund zur bestehenden Heuristik, keine Aussage über die Überlegenheit autonomer Hardware gegenüber beliebigen EMS-Systemen.",
        "",
        "## PV-only und Speichermehrwert",
        "",
        "Die ursprüngliche PV-only-Referenz hat kein konfiguriertes AC-Limit; das Speicherpaket teilt 800 W für PV und Entladung. Dessen ursprünglicher Mehrwert enthält deshalb System-/Wechselrichterunterschiede. Für einen kontrollierteren Speichervergleich wird zusätzlich ausschließlich die PV-only-Referenz auf dasselbe bereits konfigurierte AC-Limit gesetzt. Das ist ein gesondertes Diagnoseexperiment, keine Änderung der 13 Szenarien und keine Behauptung zur realen Wechselrichtertopologie.",
        "A/B verwenden dieselbe autonome E3/DC-PV-only-Referenz; C verwendet eine ebenfalls ideale E3/DC-PV-only-Referenz, damit dessen Steuerungsvorteil nicht dem Speicher zugeschlagen wird.",
        "",
        "| Ausbau / Variante | PV-only Kosten EUR | Mit Speicher EUR | Ursprünglicher Paketmehrwert Cash / Endwert EUR | Speichermehrwert bei gleichem AC-Limit Cash / Endwert EUR |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in refs["storage_comparisons"]:
        lines.append(
            f"| {r['expansion']} / {r['model']} | {n(r['pv_only_net_cost_eur'])} | {n(r['pv_with_storage_net_cost_eur'])} | {n(r['package_increment_cash_eur'])} / {n(r['package_increment_inventory_eur'])} | {n(r['same_ac_storage_increment_cash_eur'])} / {n(r['same_ac_storage_increment_inventory_eur'])} |"
        )
    lines += [
        "",
        "## Investitionen und Entscheidung",
        "",
        "2.500 EUR sind weiterhin die Annahme für das gesamte Paket 2 kWp + 5 kWh, nicht automatisch der isolierte Speicherpreis. Die PV-only-Kosten fehlen; damit ist der Speicher-CAPEX-Aufpreis unbekannt. Bei 3 kWp fehlen zusätzlich die Mehrkosten, bei 6 kWp beide vergleichbaren Angebote und die genaue Topologie.",
        "Speichermehrinvestition = Paketpreis − vergleichbarer PV-only-Preis. Wirtschaftlichkeit erfordert über die Nutzungsdauer zusätzliche Nettoersparnisse plus Restwert, die diesen Aufpreis einschließlich Betrieb/Wartung und Finanzierung decken. Positive fünf Tage erfüllen diesen Nachweis nicht.",
        "Die Modellwerte rechtfertigen noch keine Kaufentscheidung. PV-only liefert bereits einen erheblichen Teil des Zusatznutzens; der kleine zusätzliche Speicherertrag muss gegen einen erst zu belegenden Aufpreis stehen. Zuerst die reale Bestandsregelung und Messgrenzen absichern, statt weitere MaxxiCharge-Funktionen zu entwickeln.",
        "Keine Jahresrendite, Amortisationszeit oder wirtschaftliche Überlegenheit aus fünf Novembertagen. Ergebnisse bleiben VORLÄUFIG.",
        "",
        "Stündliche Original-/Modellflüsse und Kosten: baseline-hourly.csv. Detailvergleiche: storage-comparison.csv. Reproduzierbarer Diagnosebeleg: diagnosis.json und manifest.json.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--simulation-dir", required=True)
    parser.add_argument("--hourly-source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        output = Path(args.output)
        if output.exists() or output.is_symlink() or not output.parent.is_dir():
            raise ValueError("New private output directory required")
        prepared, _ = read_json(args.prepared)
        checked = verify_prepared(prepared)
        simulation_dir = Path(args.simulation_dir)
        result, result_sha = read_json(simulation_dir / "simulation.json")
        data, data_sha = read_json(simulation_dir / "normalized-input.json")
        validate_sim_report(result)
        if (
            digest(data) != result["input_sha256"]
            or data["measurement_preparation"]["source_sha256"] != checked["source_sha256"]
            or data["measurement_preparation"]["mapping_sha256"] != checked["mapping_sha256"]
        ):
            raise ValueError("Stored result is not bound to these measured inputs")
        raw = Path(args.hourly_source).read_bytes()
        if hashlib.sha256(raw).hexdigest() != prepared["source_file_sha256"]:
            raise ValueError("Original hourly source differs")
        original = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        baseline = baseline_diagnosis(
            checked["rows"],
            result["scenarios"]["e3dc"]["rows"],
            data["rows"],
            original,
            data["e3dc"],
        )
        diagnostic = {
            "status": "provisional",
            "historical_acceptance_passed": False,
            "source_result_sha256": result_sha,
            "source_normalized_sha256": data_sha,
            "source_hourly_sha256": hashlib.sha256(raw).hexdigest(),
            "diagnostic_code_sha256": hashlib.sha256(
                Path(__file__).read_bytes().replace(b"\r\n", b"\n")
            ).hexdigest(),
            "baseline": baseline,
            "experiments": reference_experiments(data, result),
        }
        artifacts = {
            "diagnosis.json": canonical(diagnostic),
            "baseline-hourly.csv": to_csv(baseline["rows"]),
            "storage-comparison.csv": to_csv(diagnostic["experiments"]["storage_comparisons"]),
            "report.md": markdown(diagnostic, result).encode("utf-8"),
        }
        output.mkdir(mode=0o700)
        for name, content in artifacts.items():
            with (output / name).open("xb") as handle:
                handle.write(content)
        with (output / "manifest.json").open("xb") as handle:
            handle.write(
                canonical(
                    {
                        "complete": True,
                        "artifacts_sha256": {
                            name: hashlib.sha256(raw).hexdigest() for name, raw in artifacts.items()
                        },
                    }
                )
            )
        print("Read-only diagnosis complete; originals and stored scenarios unchanged")
        return 0
    except (ValueError, OSError, KeyError, TypeError, csv.Error):
        print("Diagnosis failed; no original or existing result overwritten")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

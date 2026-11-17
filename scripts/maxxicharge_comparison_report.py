"""Render existing Phase-2 results; never rerun or change economic calculations."""

import argparse
from pathlib import Path

from ems_maxxicharge.inputs import read_json
from eos_pv_helper.dashboard_view import validate_sim_report


def render(result):
    validate_sim_report(result)
    if result.get("simulation_schema") != 2:
        raise ValueError("Phase-2 result required")
    audit = result.get("historical_audit") or {}
    preparation = result.get("measurement_preparation") or {}
    measured = audit.get("reference_totals", {})
    cases = result["scenarios"]
    base = cases["e3dc"]["summary"]

    def fmt(value, digits=2):
        return "offen" if value is None else f"{value:.{digits}f}".replace(".", ",")

    lines = ["# MaxxiCharge-Vergleich · " + ("VORLÄUFIG" if not audit.get("historical_acceptance_passed") else "SIM"),
             "", f"Zeitraum UTC: {result['start_utc']} bis {result['end_utc']} · {fmt(result['coverage_hours'], 0)} Stunden.",
             "", "Alle Ersparnisse sind Modellvergleiche zur simulierten Bestandsreferenz; keine realisierte Ersparnis.",
             "", "## Datenqualität", "", audit.get("message", "Keine historische Abnahme dokumentiert."),
             "", "Historische Abnahme bestanden: " + ("ja" if audit.get('historical_acceptance_passed') else "nein") + "."]
    if preparation:
        q = preparation["audit"]
        lines += [f"Energie-/Tarifintervalle vollständig: {q['energy_complete_intervals']}/{q['intervals']}.",
                  f"Verbrauch: {fmt(measured.get('load_wh', 0) / 1000, 6)} kWh."]
        if preparation.get("interval_mean_power_derived"):
            lines += ["Fahrzeugenergie: aus original gespeicherten Intervall-Leistungsmittelwerten abgeleitet; keine Linksrechteckintegration von Momentanwerten und keine direkte Intervallenergiemessung.",
                      "Die Abdeckung importierter Aggregate ist eine Angabe des Originalexports; einzelne Mittelwerte wurden hier nicht erneut aus der HA-Datenbank abgerufen."]
    if audit.get("soc_audit"):
        soc = audit["soc_audit"]
        lines += [f"SoC: {soc['missing_or_stale_start_points']} Start- und {soc['missing_or_stale_end_points']} Endpunkte fehlen oder sind zu alt. {soc['usable_intervals']} Intervalle haben beidseitig gültige SoC-Punkte.",
                  "Veraltete Punkte wurden nicht ersetzt, interpoliert oder zur Kalibrierung umdatiert."]
    if audit.get("site_balance_audit"):
        b = audit["site_balance_audit"]
        lines += [f"Standortbilanz: {b['failed_intervals']} Intervalle über der unveränderten strengen Toleranz von {fmt(b['strict_tolerance_wh'])} Wh; maximal {fmt(b['max_abs_error_wh'])} Wh, Summe Bilanz minus Verbrauch {fmt(b['sum_error_wh'])} Wh."]
    fit = audit.get("efficiency_fit", {})
    if fit:
        lines += [f"Wirkungsgraddiagnose: {fit.get('status')}; nicht auf die Simulation angewandt."]
    lines += ["", "## Kostenreferenz", "",
              f"Gemessene LUOX-Bezugskosten vor Einspeiseerlös: {fmt(measured.get('grid_cost_eur'))} EUR.",
              f"Gleicher gemessener Bezug zu 0,32 EUR/kWh: {fmt(measured.get('fixed_grid_cost_eur'))} EUR.",
              f"Simulierter Bestand: Bezugskosten {fmt(base['grid_cost_eur'])} EUR; Kosten nach Einspeiseerlös einschließlich konfiguriertem Verschleiß {fmt(base['operating_cost_eur'])} EUR.",
              "Die Modellreferenz bildet den tatsächlich gemessenen E3/DC-Betrieb nicht kalibriert nach. Eine Ersparnis gegenüber dieser Referenz ist keine gemessene Anlagenersparnis.",
              "", "## Alle Szenarien", "",
              "Kosten und Ersparnisse gelten ausschließlich für den dargestellten Zeitraum. Speichermehrwert vergleicht identische Zusatz-PV mit passender Vergleichssteuerung; beim Idealmodell wird auch die PV-ohne-Zusatzspeicher-Referenz ideal optimiert.", "",
              "| Szenario | Netzbezug kWh | Kosten EUR | Ersparnis Cash EUR | Ersparnis endwertbereinigt EUR | Speichermehrwert endwertbereinigt EUR | Zusatzinvestition EUR |",
              "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    order = ["e3dc", "pv2_only", "pv2_bat5__autonomous", "pv2_bat5__coordinated", "pv2_bat5__ideal",
             "pv3_only", "pv3_bat5__autonomous", "pv3_bat5__coordinated", "pv3_bat5__ideal",
             "pv6_only", "pv6_bat10__autonomous", "pv6_bat10__coordinated", "pv6_bat10__ideal"]
    for key in order + sorted(set(cases) - set(order)):
        if key not in cases:
            continue
        case = cases[key]
        s = case["summary"]
        label = case["label"].replace("|", "/")
        investment = fmt(s.get("investment_eur"), 0)
        if s.get("investment_eur") is None and s.get("investment_base_eur") is not None:
            investment = fmt(s["investment_base_eur"], 0) + " + unbekannte Mehrkosten"
        storage = fmt(s.get('storage_increment_inventory_adjusted_eur')) if case.get('maxxi_config') else "entfällt"
        lines.append(f"| {label} | {fmt(s['grid_import_wh'] / 1000, 3)} | {fmt(s['operating_cost_eur'])} | "
                     f"{fmt(s['savings_cash_eur'])} | {fmt(s['savings_inventory_adjusted_eur'])} | "
                     f"{storage} | {investment} |")
    lines += ["", "## Annahmen und Interpretation", "",
              "A = autonome Regler, B = EMS-Grenzen mit interner Regelung, C = theoretische Idealsteuerung mit perfekter Kenntnis der Eingangsreihe. Keine Variante ist hier als reale Hardwaresteuerung bestätigt.",
              "2.500 EUR sind die bestehende Annahme für 2 kWp + 5 kWh. Kosten für PV-only, 3-kWp-Mehrkosten und die 6-kWp-/10-kWh-Topologie bleiben offen. Unbekannt bedeutet nicht kostenlos.",
              f"Endwert: {fmt(result['config']['terminal_value_eur_kwh_ac'])} EUR/kWh nutzbare AC-Energie. Cash-Ersparnis und Endwertkorrektur bleiben getrennt.",
              "Zusatz-PV ist simuliert, einschließlich Geometrie-/Wetterproxy und Bifazialitätsannahmen. Speicherwirkungsgrade, Reglerreaktion und AC-Grenzen sind unveränderte Modellannahmen; kein Fit an veraltete SoC-Werte.",
              "Optionale Netzladeannahmen aktiv: " + ("ja" if result['config']['operation']['optional_grid_charging'] else "nein") + ".",
              "Keine Jahreshochrechnung oder Amortisationsaussage aus fünf Novembertagen.", "",
              "## Reproduzierbarkeit", "", f"Run-ID: `{result['run_id']}`.",
              f"Engine-Code: `{result['engine_code_sha256']}`.",
              f"Eingabe: `{result['input_sha256']}`. Konfiguration: `{result['config_sha256']}`.", "",
              "Originale, Zuordnung, Prüfberichte und Szenariodaten bleiben im privaten Ausgabeverzeichnis. Keine produktive Installation oder Gerätesteuerung."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        result, _ = read_json(args.simulation)
        report = render(result)
        with Path(args.output).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(report)
        print("Private comparison report written; no economic recalculation")
        return 0
    except (ValueError, KeyError, TypeError, OSError):
        print("Comparison report failed; no existing report overwritten")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

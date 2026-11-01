# Plan-Ist: private Offline-Auswertung

Erweiterung des bestehenden Inspector-/Wirtschaftlichkeitsberichts. Keine neue
Weboberfläche, kein Dienst, keine Datenabfrage und keine Geräteausführung.
Die Integration wurde zuerst unabhängig abgesichert (siehe [Matrix](EMS_INTEGRATION.md)).

## Strikter Messdatenvertrag, Schema 1

Ein vorhandener privater Export enthält **gemessene Intervallintegrale in Wh**.
Die folgenden Werte sind ausschließlich ein synthetisches Formatbeispiel:

```json
{
  "schema_version": 1,
  "energy_kind": "measured_interval_wh",
  "origin": {
    "kind": "homeassistant_statistics_export",
    "source_artifact_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "pv_basis": "ac",
    "battery_basis": "dc_bus",
    "house_load_scope": "whole_site_including_loadpoints",
    "tariff_basis": "retail_final_eur_kwh"
  },
  "energy": [{
    "start_utc": "2026-10-31T12:00:00+00:00",
    "end_utc": "2026-10-31T12:15:00+00:00",
    "pv_wh": 0, "load_wh": 250, "grid_import_wh": 250,
    "grid_export_wh": 0, "battery_charge_dc_wh": 0,
    "battery_discharge_dc_wh": 0
  }],
  "soc": [{"at_utc": "2026-10-31T12:15:00+00:00", "percent": 40}],
  "tariffs": [{
    "start_utc": "2026-10-31T12:00:00+00:00",
    "end_utc": "2026-10-31T12:15:00+00:00", "retail_eur_kwh": 0.3
  }]
}
```

Weitere Quelltypen: `evcc_history_export`, `e3dc_meter_export`, `operator_meter_export`.
Hash verweist auf das unveränderte private Quellartefakt; Authentizität/Herkunft
bleiben Betreiberprüfung. Freitext, Tokens, Geräteadressen und Configs werden nicht
in den Report übernommen. Keine Aufnahme oder Reparatur von Messwerten durch dieses Modul.

Fehlende Einzelgrößen dürfen fehlen; sie bleiben unbekannt. Null ist gültig.
Negative Bezugstarife sind gültig, negative Energien oder bool/NaN nicht.
Originalzeitpunkte müssen Zeitzone/Offset enthalten; intern UTC, Anzeige Berlin.
Duplikate/Überlappung sind Fehler, Lücken bleiben Lücken. Vorzeichen und Einheit
des tatsächlichen Messpunkts sind vorher zu bestätigen.

## Zeitraster und Größen

- Nur vollständig abgedeckte native Planslots werden aggregiert. Vier Viertelstunden
  dürfen eine Stunde bilden; eine gemessene Stunde wird nicht auf Viertelstunden verteilt.
- Keine W→Wh-Integration, keine Differenzen unbestätigter/resettender Zähler und
  keine künstliche Verschiebung historischer Zeitstempel. Ein Exportadapter muss
  diese Herkunft bereits belegen, statt hier fehlende Werte zu erfinden.
- Hausverbrauch umfasst dieselben Verbraucher wie die EOS-Last. evcc-Home-Power
  kann Loadpoints ausschließen; ohne bestätigten Scope keine Summierung/Fehlerkennzahl.
  Batterieladung gehört nicht nochmals zur Hausverbrauchsreihe.
- PV-Vergleich nur bei AC-Messpunkt; Batterievergleich nur bei bestätigtem DC-Bus.
  Native Batterieladung ist DC-Energie vor internem Ladewirkungsgrad, Entladung
  die gelieferte DC-Energie nach internem Entladewirkungsgrad. Keine Faktoren→kW-Abkürzung.
- SoC am Slotende: vorhandener Messpunkt davor, höchstens 60 s alt; Originalzeit
  und Abstand bleiben erhalten. Kein Interpolieren, kein Verwenden späterer Punkte.
  Diese Diagnosegrenze verändert nicht die 300-s-Dispatch-Sicherheitsgrenze.
- Abgeschlossene Messintervalle und SoC-Punkte in der Zukunft werden abgelehnt;
  ein Forecast wird durch eine Herkunftsdeklaration nicht zu einem Ist-Wert.

## Kosten und Interpretation

Netzbezugskosten = tatsächlich erfasste Bezugsmengen × zugehöriger finaler Tarif.
Ein Preis muss das gesamte gemessene Energieintervall abdecken. Bei grobem
Stundenzähler und wechselnden Viertelstundenpreisen wird keine gleichmäßige
Energieverteilung unterstellt: Kosten nicht berechenbar. Keine stillschweigende
Null für fehlende Tarife. Keine Modell-LCOS, Batterie-Endwerte, Grundgebühren oder
unbelegte Einspeisetarife in die gemessenen Bezugskosten hineinmischen.

PV-/Lastabweichungen sind Forecast-Diagnosen. Abweichender Netzbezug/SoC gegenüber
einem **nicht ausgeführten** GENETIC-Plan beweist keinen Regler- oder Modellfehler.
Die Referenzanzeige ist ebenfalls zunächst forecastbasiert; Hersteller-Standardmode
muss bestätigt und Forecastfehler müssen getrennt werden, bevor physikalische
Modellkalibrierung beansprucht wird. `realized_savings_eur` bleibt ausdrücklich
`null` (unbekannt), nicht 0 EUR.
Gemessene Kosten sind keine gemessene kontrafaktische EMS-Mehrersparnis.

## Ausführung nach privatem Export

Auf dem Diagnose-Rechner dieselbe isolierte Umgebung wie im
[Wirtschaftlichkeitsrunbook](ECONOMICS_COMPARISON.md) verwenden. Keine produktive
Konfiguration, kein Docker-Socket und keine schreibbaren Quellmounts. Zusätzlich
zum vorhandenen Vergleichsexport die private Messdatei read-only mounten:

```sh
set -o noclobber
docker run --rm --pull=never --network none --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --tmpfs /tmp:rw,nosuid,nodev \
  --tmpfs /tmp/eos-test:rw,nosuid,nodev \
  --mount type=bind,source=/PRIVATE/comparison-inputs.json,target=/private/inputs.json,readonly \
  --mount type=bind,source=/PRIVATE/actuals.json,target=/private/actuals.json,readonly \
  --entrypoint python eos-economics:review \
  -m eos_pv_helper.economics_report --input-report /private/inputs.json \
  --actuals /private/actuals.json --format html > /PRIVATE/plan-actual-NEW.html
```

Exitcode 0: native Vergleichspläne berechenbar und Bezugskosten bei angefordertem
Ist-Vergleich vollständig gedeckt. 2: gültiger Report mit Datenlücken; 1: ungültiger
Eingang, keinen Teilreport verwenden. Zusätzlich `--format json` für einen neuen
privaten Prüfbericht. Quellartefakte und Hashes erhalten; HTML lokal öffnen.

Aktuell ist kein vollständiger normalisierter Realexport vorhanden. Die belegten
[Bestände und Zugriffsgrenzen](HISTORICAL_ACTUALS_INVENTORY.md) bleiben sichtbar;
synthetische Tests ersetzen keine reale Abnahme. Kein Token, Archiv oder Report auf GitHub.

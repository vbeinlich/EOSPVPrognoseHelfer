# Gemeinsame Energie-Datenaufbereitung

Stand 17.11.2026, Erweiterung auf PR #30. Historische Exporte und fortlaufende
Messwerte verwenden `eos_pv_helper.energy_data.prepare`. Der Simulator erhält
dieselben geprüften Intervalle über `--input-kind prepared`; die vorhandenen
PV-, Batterie-, MILP- und Kostenmodelle werden nicht ersetzt. Der alte
Stunden-CSV-Import verwendet dieselbe AC/DC-Konvertierung und Standortbilanz.
Es wird kein produktiver Sammler, HA-Zugang oder Scheduler installiert.

## Zuordnung und Grenzen

`simulator/energy-mapping.example.json` bildet die mitgeteilte Installation ab:

| Größe | Quelle |
| --- | --- |
| Haus ohne WP und Scheunen-EV | `sensor.em_hausverbrauch_energie` |
| Wärmepumpe | `sensor.em_mtec_energie` |
| Scheunen-EV | `sensor.evcc_scheune_charge_power` |
| Bestands-PV | `sensor.em_pv_energie` |
| Netzbezug / Einspeisung | `sensor.em_netzbezug_energie` / `sensor.em_netzeinspeisung_energie` |
| Batterieladung / Entladung | `sensor.em_batterie_ladung_energie` / `sensor.em_batterie_entladung_energie` |
| Bezugskosten | `sensor.luox_netzbezugskosten_gesamt` |
| Batterie-SoC | `sensor.evcc_battery_soc` |

Standortverbrauch = Haus + WP + Scheunen-EV. `sensor.evcc_m_tec_evcc_charge_power`
steht in `excluded_entities`: seine Verwendung würde die WP doppelt zählen.
Diese Sperre ist installationsspezifische Konfiguration, keine Sonderregel im
Berechnungsalgorithmus. Neue Verbraucher benötigen eine zusätzliche Metrik mit
eigener `covers`-Gruppe und einen Eintrag in `load_components`. Überlappende
Gruppen, wiederholte Komponenten und derselbe Sensor in mehreren Größen werden
abgewiesen. Die Vollständigkeit der fachlichen Gruppendefinition muss der
Betreiber bestätigen; aus Sensornamen kann die Software sie nicht beweisen.

Jede Quelle deklariert `kind`, `unit` und bei Energie/Leistung `basis`. Die
Beispielwerte kWh, W und AC-Bus müssen gegen den Export bestätigt werden.
DC-PV/-Batterieentladung benötigt `inverter_dc_to_ac_efficiency`, DC-Ladung
`inverter_ac_to_dc_efficiency`. Keine impliziten 92 %, kein Wirkungsgrad-Fit
auf Messwerte. Die bestehenden Batterie-Wirkungsgradprüfungen bleiben separat.

`tariff_basis=retail_final_eur_kwh` und `grid_cost_scope=energy_import_only`
bestätigen fertige Endkundenpreise beziehungsweise ausschließlich variable
Bezugskosten. Grundgebühren, andere Verbraucher oder bereits doppelt berechnete
Aufschläge dürfen nicht in diesen Kostenzähler eingehen. Es gibt keine Änderung
der LUOX-Preisformel. Bei vorhandenem Intervallkostenzähler wird der effektive
Stundenpreis als Kosten / gemessene Bezugsenergie berechnet. Bei 0 Wh Bezug
wird kein Preis erfunden: dann ist ein expliziter gültiger Intervalltarif nötig.
Unterschiedliche Viertelstundenpreise werden nicht ungewichtet gemittelt.

## Originalbeobachtungen

UTF-8-JSON mit `observations` oder eine lange CSV mit identischen Feldnamen:

```json
{"observations": [
  {"entity_id":"sensor.em_hausverbrauch_energie",
   "at":"2026-11-10T00:00:00+01:00", "value":1234.5, "unit":"kWh"},
  {"entity_id":"sensor.em_hausverbrauch_energie",
   "at":"2026-11-10T01:00:00+01:00", "value":1234.8, "unit":"kWh",
   "received_at":"2026-11-10T01:02:00+01:00"}
]}
```

Die Werte im Beispiel sind rein illustrativ. Direkte Intervallenergien und
Tarife verwenden `start`/`end` anstelle von `at`. Mehrere Quellen einer Metrik
werden nach Intervallenergie → Zähler → Leistung priorisiert; nie addiert.
Quellverweise sind SHA256 der ursprünglichen Beobachtungen, nicht veränderliche
Positionsnummern. Die Ausgabe erhält Originalwerte und Originalzeitstempel.
`original-export.bin` erhält zusätzlich die vollständigen ursprünglichen Bytes.
Vollständige bestehende HA-History-GET-Exporte sind über `--input-kind ha_history`
lesbar; `last_updated` bleibt Beobachtungszeit, auch bei verspäteten Updates.
Minimierte History-Objekte ohne Einheit/Entity sind vorher explizit zu exportieren,
nicht stillschweigend mit geratenen Metadaten zu ergänzen.

Breite Stunden-CSVs verwenden `--input-kind wide_csv` und die deklarativen
`csv`-Spaltenzuordnungen je Quelle. `simulator/energy-wide-history.example.json`
ordnet die vorhandene NAS-Datei korrekt zu: `load_wh` → Haus, eigene optionale
Spalten `heatpump_wh` und `vehicle_barn_wh` für die beiden zusätzlichen Verbraucher.
Fehlende Spalten bleiben fehlende Messungen. Bereits durch Zählerdifferenz oder
Leistungsintegration abgeleitete Archivwerte erhalten `derivation` und werden
nicht nachträglich zu direkten Messungen erklärt. Diese Spaltenprojektion führt
keine Energieberechnung aus; danach läuft derselbe gemeinsame Adapter.

* **Zähler:** Differenz zwischen belegten Originalgrenzen. Ein über zwei Stunden
  gemessener Anstieg wird nicht auf zwei einzelne Stunden verteilt. Eine Messung
  um 01:02 wird nicht zu 01:00 umdatiert. Nur ein separat belegter ursprünglicher
  01:00-Wert mit späterem `received_at` kann diese Grenze nachträglich schließen.
  Sinkende Energiezähler oder ein explizites `reset: true` sperren das betroffene
  Intervall. Das Folgeintervall kann mit der neuen Basis wieder vollständig sein.
  Geldzähler dürfen wegen negativer Preise sinken; ihre Rücksetzungen benötigen
  deshalb ein originales Resetkennzeichen. Ein unmarkierter Geldzählerreset ist
  aus zwei Zahlen allein nicht zuverlässig erkennbar.
* **Leistung:** explizite Linksrechteckintegration (`left_hold`) zwischen
  Originalbeobachtungen, mit konfigurierter maximaler Lücke. Die Randabdeckung
  muss belegt sein. Unbekannt/Unavailable und zu große Lücken sperren die Energie.
  Es gibt keine Extrapolation über den letzten Messpunkt und keine verdeckte
  lineare Interpolation. Diese Energie bleibt sichtbar abgeleitet und vorläufig.
* **Intervallenergie:** nur vollständige Originalintervalle addieren. Grobe
  Energien niemals proportional auf feinere Intervalle verteilen.
* **Zeit:** intern ausschließlich UTC, 900- oder 3600-Sekunden-Raster. Explizite
  Offsets erhalten die beiden Berliner Herbststunden getrennt. Naive Ortszeiten
  brauchen Bestätigung; mehrdeutige und nicht existente Ortszeiten werden immer
  abgewiesen. Zukünftige Messwerte und noch nicht abgeschlossene Intervalle
  bestehen die Prüfung nicht.
* **SoC:** letzter originaler Punkt an/vor der Grenze, höchstens 60 Sekunden alt,
  mit seinem ursprünglichen Zeitpunkt. Keine zukünftigen Punkte oder Mittelwerte
  als Grenz-SoC. Benachbarte historische Grenzwerte bleiben streng geprüft.

## Qualität und gemeinsame Weiterverwendung

Jedes Intervall enthält Werte, Quellhashes, `quality`, `issues` und `status`.
Qualität unterscheidet `direct`, `derived_counter`, `derived_power_left_hold`,
DC→AC-Konvertierung, Verbrauchssumme und `incomplete`. Die Bilanz lautet:

```text
PV + Netzbezug + Batterieentladung − Einspeisung − Batterieladung − Standortverbrauch
```

Standardtoleranz 50 Wh pro Stunde, weiterhin maximal 500 Wh konfigurierbar.
Die unabhängig bilanzierte Last ersetzt niemals die Summe der Verbraucher;
beide stehen nebeneinander. Fehlende Werte bleiben leer/null. Summen haben
zusätzliche Abdeckungszähler; Teilsummen dürfen nicht als vollständige Zeiträume
gelesen werden. Abweichungen oberhalb der Toleranz sperren die Simulation.

`MeasurementBuffer.extend` nimmt neue oder verspätete Beobachtungen auf.
`prepare(..., as_of=...)` nutzt exakt denselben Pfad wie ein historischer Export.
Wiederholte Beobachtungen werden bei der Berechnung nicht doppelt gezählt.
Konflikte brauchen eindeutige ursprüngliche Revisions-/Ankunftszeiten. Frühere
Ergebnisobjekte werden nicht verändert. Ein bestehender Sammler kann diese API
aufrufen und seine Originale privat persistent halten; Langzeitaufbewahrung und
Fensterrotation bleiben bei ihm. Die begrenzte Bibliothek startet keinen Dienst.

Der komplette Original-/Mapping-/Audit-Satz wird beim Simulationsimport erneut
berechnet. Ein manuell auf „passed“ gesetzter Status reicht nicht. Bei vollständigen
gemessenen Daten entsteht außerdem `plan-actual.json` für den vorhandenen
`plan_actual.Actuals`-Reader. Dieser Export übernimmt dieselben Energien und
Preise; DC-Batteriewerte erscheinen ausschließlich bei belegten Umrechnungsfaktoren.
Synthetische oder unvollständige Daten erzeugen keinen gemessenen Plan-Ist-Export.

## Reproduzierbarer privater Ablauf

Zuerst Beispielmapping privat kopieren, Einheiten/Messgrenzen und Kostenumfang
bestätigen. Originalexport und Tarifintervalle unverändert bereitstellen.
Alle folgenden Schritte sind lokal/offline; neue Ausgabeordner verwenden.

```sh
python -m eos_pv_helper.energy_data_cli \
  --input /PRIVATE/original-observations.json \
  --mapping /PRIVATE/energy-mapping.json \
  --start 2026-11-10T00:00:00+01:00 --end 2026-11-15T00:00:00+01:00 \
  --as-of 2026-11-15T01:00:00+01:00 --output /PRIVATE/prepared-new

python scripts/check_energy_regression.py --prepared /PRIVATE/prepared-new/prepared.json

python -m ems_maxxicharge --input /PRIVATE/prepared-new/prepared.json \
  --input-kind prepared --context /PRIVATE/sim-context.json \
  --config simulator/phase2.example.json --phase2 --output /PRIVATE/comparison-new
```

Für den vorhandenen, noch unvollständigen NAS-Export stattdessen beim ersten
Befehl `--input-kind wide_csv` und
`--mapping simulator/energy-wide-history.example.json` verwenden. Dieser Lauf
liefert den Diagnoseexport und Exitcode 3, bis die fehlenden Originalgrößen
ergänzt sind; der Simulator lehnt ihn ab.

Die Aufbereitung schreibt `prepared.json`, `corrected.csv`, `audit.json`,
unveränderte Originalbytes, Mapping und ein abschließendes Prüfmanifest.
Exitcode 0 bedeutet vollständige Datenaufbereitung, 3 bedeutet gespeicherte
unvollständige/fehlerhafte Diagnostik, 2 bedeutet ungültigen Import. Das ist noch
keine historische Modellabnahme. Bestehende Ausgabeordner werden nie überschrieben.

`sim-context.json` übernimmt die bestätigten E3/DC-/PV-/Tarifangaben aus
`history-import.example.json`. Für die Novemberabnahme zusätzlich
`historical_reference: true` setzen. Damit laufen die bisherigen strengen
120-Stunden-/Referenzsummen-/SoC-/Wirkungsgrad-/Tarifprüfungen unverändert weiter.
Für Leistungsintegration ist zusätzlich `provisional_simulation_acknowledged: true`
nötig. Dann bleiben Report und HTML deutlich **VORLÄUFIG**, und
`historical_acceptance_passed` bleibt **false**, auch bei passenden Summen.
Andere historische oder zukünftige Zeitfenster verwenden denselben Adapter ohne
November-Sonderlogik; ihre historische Modellkalibrierung wird nicht behauptet.

## November-Referenz und Ausgangsbefund vor der Ergänzungsdatei

Die Betreiberaggregate stehen getrennt in
`tests/fixtures/energy-november-reference.json`. Reine Rechenprüfung:
106.360 + 114.232 + 7.348 = 227.940 Wh zusammengesetzter Verbrauch;
die unabhängige Energiebilanz ergibt 227.884 Wh, also −56 Wh Bilanz minus Summe.
Keine November-Korrektur wird auf einzelne Intervalle aufgeschlagen.

Auf der vorhandenen NAS-Freigabe wurde lesend
`ems-dashboard-review/simulation/maxxicharge-history-20261110-14.csv` gefunden:
120 Stunden, SHA256 `8e0e7c4ea50f0f6af8b15f7a3aa80ba5017be6a96521b4a94aa639e266e86771`.
Die Spalte `load_wh` enthält tatsächlich nur die 106.360 Wh Hausverbrauch.
PV/Netz/Batteriesummen bestätigen die mitgeteilten Werte; gemessene Kosten
67,17167 EUR. Die Stundenverläufe für WP und Scheunen-EV fehlen. Außerdem
sind 94 Start- und 95 End-SoC-Punkte älter als 60 Sekunden. Der vorhandene
HA-Tokenpfad ist weiterhin nicht lesbar; Rechte wurden nicht verändert.

Diese Originaldatei wurde privat unverändert gesichert und durch reine
Spaltenzuordnung in den gemeinsamen Adapter gegeben: ursprüngliches `load_wh`
→ `house_wh`, andere vorhandene Messgrößen unverändert. Die abgeleitete
Standortbilanz ergibt 227.884 Wh, ohne diese als gemessene Verbraucherkomponenten
auszugeben. Der private korrigierte **Diagnoseexport** enthält 120 Zeilen,
leere WP-/EV-/Standortverbrauchsfelder und eindeutigen Status `incomplete`.
Es gibt **keinen vollständig korrigierten Verbrauchsexport** und keine bestandene
historische Regression, solange diese Originalverläufe fehlen. Sie wurden beim
Betreiber angefragt. Der ausdrücklich übersprungene
Test `test_private_original_120_hour_regression_if_supplied` läuft erst mit
`EMS_PRIVATE_PREPARED_REFERENCE=/PRIVATE/prepared-new/prepared.json`. CI erhält
ausschließlich synthetische Daten.

Die neuen Tests prüfen gemeinsame historische/fortlaufende Berechnung, verspätete
Ankünfte und Revisionen, Quellenpriorität, Lücken, Resets, negative Kosten,
Verbraucherüberlappung, neue Verbraucher, UTC/DST, AC/DC, SoC-Zeitpunkte,
unveränderte Originale und den bestehenden 13-Szenarien-Pfad. Ein CI-Containerlauf
prüft den tatsächlich gepackten Offline-Simulator mit derselben Aufbereitung,
sichtbarer vorläufiger Leistungsintegration und unveränderten Eingangsdateien.

Keine produktive Installation, kein Containerneustart, keine Gerätesteuerung,
kein Merge und keine Image-Veröffentlichung erfolgen durch diese Änderung.

## Ergänzende Originalexporte und vorläufige Simulation

Die spätere WP-/EV-Ergänzung wird mit `eos_pv_helper.energy_join` anhand beider
Intervallgrenzen verbunden. Der Join prüft eindeutige, lückenlose und gleiche
Zeitfenster beider Dateien. Er verweigert fehlende Stunden, veränderte Endgrenzen,
Überlappungen und kollidierende Nicht-Schlüssel-Spalten. Er verändert keine
Messwerte; die ursprüngliche `load_wh`-Spalte bleibt im Join der Hausverbrauch.
Erst die bestehende gemeinsame Aufbereitung bildet daraus den Standortverbrauch.

Der Join erhält beide vollständigen Originaldateien samt Prüfsummen. Eigene
private Verzeichnisse verwenden; keine Originale ersetzen:

```sh
python -m eos_pv_helper.energy_join \
  --base /PRIVATE/base.csv --supplement /PRIVATE/wp-ev.csv \
  --start 2026-11-10T00:00:00+01:00 --end 2026-11-15T00:00:00+01:00 \
  --output /PRIVATE/join-new

python -m eos_pv_helper.energy_data_cli \
  --input /PRIVATE/join-new/joined.csv --input-kind wide_csv \
  --mapping simulator/energy-wide-history.example.json \
  --start 2026-11-10T00:00:00+01:00 --end 2026-11-15T00:00:00+01:00 \
  --as-of 2026-11-15T01:00:00+01:00 --output /PRIVATE/prepared-new

python scripts/check_energy_regression.py \
  --prepared /PRIVATE/prepared-new/prepared.json --aggregate-only
```

`--aggregate-only` prüft vollständige originale Energiesummen gegen die
Referenz, auch wenn SoC- oder Bilanzqualitätsprobleme bestehen. Der Status
`aggregate_match` ist ausdrücklich keine bestandene historische Abnahme.
Der bisherige strenge Standardaufruf bleibt unverändert.

Fahrzeugenergie aus original gespeicherten Fünf-Minuten-Leistungsmittelwerten
erhält `derived_interval_mean_power`. Sie ist weder direkte Energiemessung noch
`derived_power_left_hold` über Momentanwerte. Beim bereits aggregierten Wh-Export
fordert die Zuordnung eine ausgewiesene Abdeckung `vehicle_barn_5min_coverage`.
Nur vollständige `12/12` für eine Stunde bei 300 Sekunden Raster wird zugelassen.
Diese Information ist eine deklarierte Eigenschaft des Originalexports; sie
beweist nicht nachträglich die hier nicht mitgelieferten einzelnen Mittelwerte.
Fehlende/teilweise Abdeckung bleibt fehlende Energie. Der neue Quellentyp
`mean_power` kann auch die originalen zeitlich abgegrenzten Mittelwerte selbst
verarbeiten: Energie = Mittelwert × Originaldauer, anschließend exakte Addition.

Der Audit unterscheidet nun vollständige Energie-/Tarifintervalle, überschrittene
Standortbilanzgrenzen und gültige SoC-Intervalle. Veraltete SoC-Werte bleiben in
den Originaldaten und in den Ablehnungsdetails mit Beobachtungszeit und Alter;
sie werden nicht als gültige Grenzwerte eingesetzt.

Für den ausdrücklich beauftragten **vorläufigen** Vergleich kann die private
SIM-Konfiguration enthalten:

```json
{
  "historical_reference": false,
  "provisional_measurements_acknowledged": true,
  "provisional_max_site_balance_error_wh": 60
}
```

Diese Felder werden zu den vorhandenen bestätigten E3/DC-/PV-/Tarifangaben
ergänzt. Die Wahl von 60 Wh ist ein explizites Limit nur dieses vorläufigen
Beispiels, keine Änderung der strengen Standardtoleranz von 50 Wh. Alle
ursprünglichen Überschreitungen bleiben im Audit sichtbar. Zugelassen werden
hier ausschließlich fehlende/veraltete spätere SoC-Grenzen und begrenzte
Bilanzabweichungen. Der Anfangs-SoC muss weiterhin gültig sein. Fehlende Energien,
Tarife, Teilabdeckung, zukünftige Intervalle oder ein unbekannter Anfangs-SoC
werden auch vorläufig abgewiesen. `historical_reference=true` behält sämtliche
strengen Gates und kann nicht mit dieser Option überstimmt werden.

Die Simulation ersetzt weder spätere SoC-Werte noch Energieflüsse. Ihr Status
bleibt `warnings`, `historical_acceptance_passed=false`, und Report/HTML sind
sichtbar **VORLÄUFIG**. Eine Wirkungsgraddiagnose nutzt ausschließlich beidseitig
gültige SoC-Intervalle und wird niemals automatisch auf das Modell angewandt.

```sh
python -m ems_maxxicharge --input /PRIVATE/prepared-new/prepared.json \
  --input-kind prepared --context /PRIVATE/provisional-context.json \
  --config simulator/phase2.example.json --phase2 --output /PRIVATE/comparison-new

python scripts/maxxicharge_comparison_report.py \
  --simulation /PRIVATE/comparison-new/simulation.json --output /PRIVATE/comparison.md
```

Der Vergleichsbericht übernimmt bereits berechnete Szenariokennzahlen. Er rechnet
keinen zweiten Kostenpfad und zeigt Cash-/Endwert-Ersparnis, Speichermehrwert bei
gleicher PV-Leistung und Investitionsannahmen getrennt. Simulierte Bestandskosten
werden von gemessenen Bezugskosten abgegrenzt; die Modellreferenz ist weiterhin
nicht am realen E3/DC-Betrieb kalibriert. Keine Jahreshochrechnung aus fünf Tagen.
Die tatsächlichen Messdateien und finanziellen Vergleichsergebnisse bleiben in
privaten lokalen Artefakten; CI erhält ausschließlich synthetische Prüfdaten.

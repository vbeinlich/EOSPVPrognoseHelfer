# Phase 2 – reproduzierbarer Offline-Vergleich

Nur lokaler SIM-Service, keine Produktionsinstallation. Das bestehende
Batteriemodell, die PV-Modelle und der statische Dashboard-Renderer werden
weiterverwendet. Der neue Vergleich ergänzt sie; ohne SIM-Bericht bleibt die
Dashboard-Ausgabe unverändert. Grundlage und Herstellerannahmen:
[Phase-2-Analyse](MAXXICHARGE_PHASE2.md).

## Originaldaten und lesender Importweg

Die Original-CSV mit 120 Stunden vom **10.11.2026 00:00 bis 15.11.2026 00:00
Europe/Berlin** fehlt im zugänglichen Datenbestand. Das entspricht
`2026-11-09T23:00:00Z` bis `2026-11-14T23:00:00Z`. Die vorhandene HA-API fordert
Authentisierung; der bestehende Tokenpfad ist nicht lesbar. Es wurden keine
Rechte, Geräte, Recorder-Dateien oder produktiven Exporte verändert.

Benötigt wird der bereits erzeugte Export samt Entity-/Einheitenzuordnung und
Angaben zu Messgrenzen. Eine vorhandene Datei unverändert nach `private/` oder in
einen anderen privaten SIM-Eingangsordner übernehmen. Sie gehört nicht in Git.
Falls der bestehende Export erneut ausgeführt wird, ausschließlich die vorhandene
lesende Statistik-/History-Abfrage mit bestehenden Zugangsdaten verwenden.
HA dokumentiert hierfür den lesenden Aufruf
[`recorder.get_statistics`](https://www.home-assistant.io/actions/recorder.get_statistics/).
Konkrete Entity-IDs und der bisher verwendete Exportbefehl sind hier nicht
nachgewiesen; es wird deshalb kein geratener API-/SQL-Client eingeführt.
Für Energiewerte werden originale Intervalldifferenzen aus verifizierten
Energiezählern benötigt, keine Momentanleistung als Stundenenergie.
SOC benötigt originale Zustände an den Intervallgrenzen. Ein reiner Export von
Stundenmittelwerten ohne Herkunft/Zeitpunkte genügt der Abnahme nicht.

Die Tage 8./9.11. werden außerhalb des Prüfzeitraums verworfen. Innerhalb des
Zeitraums sind genau 120 geordnete, lückenlose Originalstunden erforderlich.
Kein Auffüllen, kein Resampling, keine aus Gesamtsummen erzeugten Messreihen.

## CSV-Vertrag

UTF-8/UTF-8-BOM, explizites Trennzeichen und Dezimalzeichen. Die Vorlage
[`history-import.example.json`](../simulator/history-import.example.json) ist
**nicht** fertig kalibriert. Private Kopie erstellen und verifizieren.
`columns` bildet kanonische Namen auf tatsächliche CSV-Überschriften ab:

| Kanonisches Feld | Bedeutung |
| --- | --- |
| `start_utc`, `end_utc` | Originalgrenzen einer vollständigen Stunde, ISO-8601 mit Offset |
| `load_wh` | Gesamtverbrauch einschließlich Ladepunkten am gleichen Standort |
| `base_pv_wh` | Bestands-PV an der erklärten AC-äquivalenten Messgrenze |
| `grid_import_wh`, `grid_export_wh` | Bezug und Einspeisung getrennt, positive Intervallenergien |
| `battery_charge_wh`, `battery_discharge_wh` | E3/DC Ladung/Entladung getrennt, Messgrenze ausdrücklich angeben |
| `import_eur_kwh`, `export_eur_kwh` | Finaler Bezugstarif/Einspeisevergütung in EUR/kWh |
| `soc_start_percent`, `soc_end_percent` | Originaler E3/DC-SOC am Anfang/Ende |
| `soc_start_at_utc`, `soc_end_at_utc` | Originalzeitstempel dieser beiden SOC-Beobachtungen |

Die sechs Energiefelder brauchen in `units` ausdrücklich `Wh` oder `kWh`.
`energy_kind=measured_interval_integrals`, `load_scope=whole_site_including_loadpoints`,
`tariff_basis=retail_final_eur_kwh` bestätigen die Mess-/Preisgrenzen.
`battery_basis=ac_bus` oder `dc_bus`; DC erfordert zusätzlich belegte
`inverter_ac_to_dc_efficiency` und `inverter_dc_to_ac_efficiency`.
SOC-Beobachtungen dürfen höchstens 60 Sekunden vor ihrer Grenze liegen, niemals
danach; benachbarte SOC-Grenzen müssen übereinstimmen. UTC-naive Zeiten erfordern
eine explizite Ortszeitbestätigung, mehrdeutige Zeiten werden abgewiesen.

LUOX: keine bloßen Börsen-/Nettopreise als Endkundentarif verwenden.
`tariff_aggregation` ist `constant_within_hour` oder `energy_weighted_hour`.
Eine bestätigte Näherung `hourly_mean_approximation_acknowledged` bleibt sichtbar
und verhindert die uneingeschränkte historische Abnahme. Bei Viertelstundenpreisen
und nur Stundenenergie kann keine exakte viertelstündliche Abrechnung behauptet werden.

Pro Stunde werden Standortbilanz (Standardtoleranz 50 Wh) und modellierte
SOC-Änderung (Standardtoleranz 200 Wh) geprüft. Toleranzen sind dokumentierte
Messannahmen, höchstens 500 Wh. Standortfehler brechen ab, SOC-/Tarif-/nicht
identifizierbare Wirkungsgrade ergeben Warnungen und keine bestandene historische
Abnahme. Wirkungsgrad-Fit ist nur Diagnose und wird nicht automatisch übernommen.
E3/DC-Kapazität 13 kWh und Wirkungsgrade/Messgrenzen müssen bestätigt werden;
92 % in der Vorlage sind keine nachgewiesenen E3/DC-Messwerte.

Die importierten Summen werden gegen die mitgeteilten fünf Referenzwerte geprüft
(50 Wh bzw. 0,15 EUR Toleranz). Abweichungen erst am Originalexport erklären,
keine künstliche Anpassung der Reihe. Ein fehlgeschlagener Lauf erzeugt keinen
vollständigen Ergebnisreport. `data_kind=synthetic` ist ausschließlich für Tests
und wird niemals als bestandene Messdatenabnahme ausgewiesen.

## SIM-PV und Modelle

Zusätzliche PV: je 1 kWp Südhütte Süd/14° und Südzaun Süd/90°, proportional auf
3 bzw. 6 kWp skaliert. Bifazialer Mehrertrag bleibt über die bestehenden
Panelparameter konfigurierbar. Private Standortkoordinaten und Bestandsausrichtung
in `pv_source` eintragen. Vorhandene archivierte Wetter-/Prognosedaten können
über `weather`/`cached_planes` wiederverwendet werden; ohne solche Originaldaten
benutzt `reference_proxy` die gemessene Bestands-PV mit ausdrücklich bestätigter
Geometrienäherung (`proxy_acknowledged=true`). Das ist **SIM**, keine Messung der
neuen Flächen. Die Vorlage lässt Geometrie und Zustimmung bewusst offen.

13 Standardzeilen: Bestand; 2/3/6 kWp ohne Speicher; 2/3 kWp +5 kWh und
6 kWp +10 kWh jeweils A/B/C. `operation.optional_grid_charging=true` ergänzt neun
separat gekennzeichnete Annahmevarianten (22 Zeilen), standardmäßig aus.
`operation.e3dc_coordination_enabled` ist standardmäßig aus.

A/B verwenden kleine SIM-Zeitschritte bei innerhalb jeder Originalstunde
konstanter Last/PV. Die angenommene Reglerreaktion ist keine nachgebildete Firmware.
C verwendet einen nachweislich optimal gelösten stündlichen MILP mit perfektem
Vorwissen. Bei Zeitlimit/fehlendem Optimalitätsnachweis kein Ersatzwert. Seine
Schranke gilt für diese diskrete Modellformulierung, nicht als Beweis über
unbekannte reale Firmware oder jede mögliche unterstündliche Regelung.

Keine AC-Aufnahme von fremder Batterieenergie durch E3/DC wird angenommen.
`battery_transfer_wh=0` ist deshalb eine Modellgrenze, kein Nachweis realer
Transferfreiheit. A kann durch unabhängige Regler Batterieeinspeisung verursachen;
sie wird bilanziert. Maxxi-PV und Batterie teilen das konfigurierte AC-Limit
(Standard 800 W); nicht nutzbarer Überschuss wird als Abregelung ausgewiesen.
Der PV-ohne-Speicher-Wechselrichter hat separat konfigurierbare Grenzen.

## Kostenabgrenzung

[`phase2.example.json`](../simulator/phase2.example.json): 2.500 EUR PoC-Annahme,
PV-only-Preis und Mehrkosten für 3 kWp bleiben unbekannt (`null`), bis eingetragen.
Beispiel: `operation.pv_only_2kwp_investment_eur=1000` und
`operation.additional_3kwp_cost_eur=400` ergeben 1.400 EUR für 3 kWp PV-only und
2.900 EUR für 3 kWp +5 kWh. Das sind Konfigurationsbeispiele, keine Angebote.
`investments_eur` erlaubt explizite Werte je Ausbau einschließlich 6 kWp.

`net_electricity_cost_eur = LUOX-Bezugskosten − Einspeiseerlös`;
`operating_cost_eur` addiert optionale modellierte Verschleißkosten.
Ersparnis ist die Differenz der Betriebskosten zum simulierten Bestand.
Festpreisvergleich rechnet denselben Bezug mit 0,32 EUR/kWh; Grundgebühren fehlen.
Speichermehrwert vergleicht identische PV-Leistung ohne Zusatzspeicher. Für C wird
dafür auch der PV-only-E3/DC ideal optimiert, damit dessen Steuerungsvorteil nicht
als Zusatzspeichergewinn zählt. Anfangs-/Endenergie und alternativ
endwertbereinigte Kosten stehen im JSON; die Dashboard-Tabelle zeigt Zeitraum-Cashflow.
Ein anderer End-SOC ist kein dauerhaft erwirtschafteter Gewinn. Keine Jahres-
oder Amortisationsaussage aus fünf Novembertagen.

## Offline-Image und Start

Die isolierte Simulation verwendet optional NumPy/SciPy/HiGHS; die produktiven
Helper-Abhängigkeiten bleiben unverändert. Hash-gepinnte Linux/CPython-3.11-Wheels
einmal auf dem Entwicklungsrechner vorbereiten. Dieser separate Download baut
keinen Geräte-/Brokerpfad auf. Cache ist ignoriert und gelangt nicht in Git:

```powershell
python -m pip download --only-binary=:all: --platform manylinux_2_27_x86_64 --python-version 311 --implementation cp --abi cp311 --dest simulator/.wheels -r simulator/requirements.txt
docker build --network none --pull=false -f simulator/Dockerfile -t ems-maxxicharge-simulator:phase2-local .
```

Build und Laufzeit behalten `network=none`; Installation aus lokalem Cache mit
`--no-index --require-hashes`. Basisimage muss bereits lokal vorhanden sein.
Keine Änderung des produktiven Compose, kein Image-Push/Deployment.

Für die geprüfte Original-CSV den vorhandenen Elternordner des neuen Outputs
vorbereiten und ausschließlich separate SIM-Pfade mounten:

```powershell
docker run --rm --network none --read-only --user 10001:10001 --cap-drop ALL --security-opt no-new-privileges --memory 384m --cpus 0.5 --pids-limit 32 --mount type=bind,source=C:\SIM\input,target=/input,readonly --mount type=bind,source=C:\SIM\output-new,target=/output ems-maxxicharge-simulator:phase2-local --phase2 --input /input/original.csv --input-kind history_csv --context /input/context.json --config /input/config.json --output /output/run
```

Pfade sind Platzhalter. Output muss neu sein, Ordner disjunkt, UID 10001 benötigt
nur dort Schreibrechte. Auf Unraid keine Rechte produktiver Ordner anpassen.
Für bereits normalisierte geprüfte Eingaben unterstützt der getrennte Service
`simulator/compose.yaml` weiterhin `input.json`/`config.json`; `SIM_INPUT_DIR` und
`SIM_OUTPUT_DIR` explizit auf neue SIM-Ordner setzen. Kein Autostart, keine Ports,
Geräte, Secrets, Docker-Sockets oder Produktionsabhängigkeiten.

`manifest.json` entsteht zuletzt und bindet `simulation.json`, `normalized-input.json`,
`mqtt-sim.jsonl`, `index.html` per SHA-256. Nur vollständige Läufe anzeigen.
Die lokale HTML-Datei enthält das bestehende SIM-Panel mit allen Vergleichszeilen.
Kein produktiver Publisher wurde ausgeführt. Nach Import ist zuerst
`historical_audit.historical_acceptance_passed` samt Warnungen und Originalsummen
zu prüfen; ein technisch erfolgreicher Containerlauf allein ist keine historische
Wirtschaftlichkeitsabnahme.

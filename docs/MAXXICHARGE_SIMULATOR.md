# MaxxiCharge V2 Plus: isolierter Multi-Battery-PoC

[Bestand und ursprünglicher Plan](MAXXICHARGE_PLAN.md),
[MQTT-Adaptervertrag](MAXXICHARGE_MQTT.md),
[Test-/Abnahmebericht](MAXXICHARGE_VALIDATION.md).

Der PoC ist ein eigenständiger Offline-Docker-Service
`ems-maxxicharge-simulator`. Er verändert keine produktive Konfiguration,
Container, Zeitpläne, EOS-Pläne oder Geräte. Ein Lauf verarbeitet einen
vollständigen gespeicherten Zeitraum und beendet sich. Kumulierte Werte gelten
für genau diesen Zeitraum; überlappende Prognoseläufe werden nicht addiert.

## Modell und Koordination

Default: 5.000 Wh interne Kapazität, 10 % Reserve/Start-SOC, 100 % Maximum,
0–800 W AC-Entladung, 92 % Wirkungsgrad pro Richtung. PV-Ladelimit 2.000 W,
AC-Netzladelimit 800 W und Verschleißkosten 0 EUR/kWh sind **Annahmen**, keine
behaupteten Gerätespezifikationen. Alle Werte sind in
[`simulator/config.example.json`](../simulator/config.example.json) konfigurierbar.
Der minimale SOC ist unantastbar; initiale nutzbare Energie wird getrennt geführt.

Alle Standortflüsse verwenden eine AC-äquivalente Wh-Bilanz; Batteriestände sind
interne Wh. Für einen Slot mit Dauer `dt`:

```text
P × dt[h] = Energie[Wh]
E_end = E_start + (PV-Ladung + Netzladung) × eta_charge − AC-Entladung / eta_discharge
Verlust = Ladung × (1 − eta_charge) + AC-Entladung × (1 / eta_discharge − 1)
PV + Netzbezug + E_start = Hauslast + Einspeisung + E_end + Verluste
```

Jede Speicher-/Standortbilanz wird rechnerisch kontrolliert, auch kumuliert.
Herkunftspools: Bestands-PV, Zusatz-PV, Netz, initialer Bestand. Entnahmen werden
proportional aus den aktuellen Pools gebucht. PV-/Netzladung bleiben separat.

1. Bestands-PV deckt Hauslast, Zusatz-PV den verbleibenden direkten Bedarf.
2. Überschuss der eigenen Zusatz-PV lädt bevorzugt MaxxiCharge. Bestands-PV-
   Überschuss lädt E3/DC. Im PoC werden nicht aufnehmbare Überschüsse eingespeist;
   keine nachträgliche Umladung oder Ladung von Maxxi aus Bestands-PV.
3. Bei Restlast entlädt Maxxi variabel bis 800 W, E3/DC deckt den Rest im Modell.
   Jede Entladung endet beim Hausbedarf; Batterieexport ist ausgeschlossen.
4. Preisladung prüft einen begrenzten zukünftigen Preis-/Bedarfszeitraum inklusive
   Roundtrip-Verlusten, Verschleiß und Mindestspread. Bereits verfügbare E3/DC-
   Energie wird abgezogen, erwartete eigene PV-Ladung erhält freien Platz.
   Bei Netzladung entlädt keiner der beiden Speicher im gleichen Slot.

Das ist eine deterministische Vorschauheuristik mit Kenntnis der gelieferten
Reihe, kein global optimaler Solver und kein realer Regler. Der E3/DC-Bestand
wird mit denselben Parametern in allen vier Fällen als Eigenverbrauchsreferenz
simuliert; es ist kein nativer Replay der Hersteller-/EOS-Steuerung.

## PV und vorhandene Datenquellen

Südhütte: 1.000 Wp, 180° Azimut, 14° Neigung. Südzaun: 1.000 Wp, 180°, 90°.
Azimutkonvention: Nord=0°, Ost=90°, Süd=180°, West=270°.

- `cached_weather`: vorhandene mittlere GHI/DNI/DHI-Strahlung und Sonnenposition
  pro Originalintervall; geometrische Transposition mit isotropem Himmel und
  Bodenreflexion. Front-Ertrag × Wp × Performance Ratio × Intervallzeit.
- `cached_planes`: bereits gespeicherter Front-Ertrag in AC-äquivalenten
  Wh/kWp, mit exakt passender Flächengeometrie. Keine zweite Performance-Ratio
  anwenden; sie ist schon im gelieferten Ertrag enthalten.
- `reference_proxy`: **nur nach expliziter Bestätigung**. Wiederverwendet die
  Wetter-/Zeitform der Bestandsprognose und schätzt die Geometrieänderung aus
  Sonnenposition, angenommenem Diffusanteil und Albedo. Keine neue Wetterabfrage.
  Standort/Referenzfläche stammen aus einer vorhandenen gespeicherten Konfiguration.
  Der Orientierungsquotient wird begrenzt, nachts ist der Proxy Null. Kein Ersatz
  für validierte Flächenprognosen; keine Rekonstruktion unbekannter Verschattung.

Bifazialer Mehrertrag ist je Fläche ein konstanter konfigurierbarer Multiplikator
`1 + bifacial_gain` (Default 0). Das ist eine Sensitivitätsannahme, kein gemessener
Rückseiten-Ertrag. Im 6-kWp-Vergleich werden beide 1-kWp-Profile mit drei skaliert;
es wird keine neue unbestätigte Montagefläche erfunden.

Der 800-W-Grenzwert betrifft im PoC die **Batterieentladung**. Ein gemeinsames
MaxxiCharge-PV-/Batterie-Wechselrichterlimit, MPPT-, Temperatur-, Standby- und
Verschattungsverhalten sind noch kein validiertes Hardwaremodell. Vor einer
Investitionsentscheidung sind diese Grenzen und die PV-Topologie zu kalibrieren.

Formeln: [pvlib Gesamtstrahlung](https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.get_total_irradiance.html),
[NOAA Näherung der Sonnenposition](https://gml.noaa.gov/grad/solcalc/solareqns.PDF).
Keine Bibliotheks-/Cloudanfragen zur Laufzeit.

## Eingangsvertrag

JSON `schema_version=1`, `energy_basis=ac_equivalent_wh`,
`data_kind=synthetic|archived_forecast|measured`, ursprüngliche `source_sha256`,
`load_scope=whole_site_including_loadpoints`, `tariff_basis=retail_final_eur_kwh`,
ein explizites `e3dc`-Batteriemodell, `pv_source` und vollständige `rows`.
Jeder Slot enthält:

```json
{
  "start_utc": "2026-06-18T12:00:00+00:00",
  "end_utc": "2026-06-18T12:15:00+00:00",
  "load_wh": 250,
  "base_pv_wh": 100,
  "import_eur_kwh": 0.3,
  "export_eur_kwh": 0.08,
  "weather": {
    "basis": "interval_mean_w_m2", "ghi": 600, "dni": 700, "dhi": 100,
    "solar_elevation_deg": 45, "solar_azimuth_deg": 180
  }
}
```

Das ist ein synthetisches Formatbeispiel. Zeitpunkte müssen einen Offset tragen;
intern wird UTC verwendet. Nur vollständige 15-/60-Minuten-Intervalle, keine
Duplikate, Überlappung oder Lücken. Keine W-Samples integrieren, Zählerstände
differenzieren, Stundenenergie auf Tarifviertelstunden verteilen oder fehlende
Werte mit Null ergänzen. Bool/NaN/Infinity und negative Energien sperren den Lauf;
negative Strompreise sind gültig. Maximal 35.136 Intervalle, Dateigröße begrenzt.
Für große Jahresdateien sind die Container-Speichergrenzen gesondert zu bemessen.

`--input-kind actuals` übernimmt den vorhandenen Vertrag aus
[PLAN_ACTUAL.md](PLAN_ACTUAL.md) über dessen Validator. Ein Preis muss das gesamte
gemessene Intervall decken. E3/DC-Parameter und belegter Einspeisetarif stehen im
privaten Kontext; Wetter/Flächen nur bei exakt gleichen Intervallzeitpunkten
zuordnen. Dies ist ein lesender Datei-Adapter, kein HA-Recorder-/SQL-Exporter.

`--input-kind eos` übernimmt die **damaligen** PV-/Last-/Preiseingaben aus der
gespeicherten Antwort, nur im Kontrollhorizont. EUR/Wh wird einmal mit 1.000 in
EUR/kWh umgerechnet. Ein expliziter Kontext bestätigt Modellannahmen zu
Gesamtlast und PV-Konversion; kombinierte konstante Batterie-/Inverterwirkungsgrade
werden ausgewiesen. Kein nativer E3/DC-Nachweis, keine gemessene Last und keine
Ausführungsquittung. Heutige `prices.json`/`forecast.json` ersetzen keine alten Daten.

## Lokal reproduzieren

Aus dem separaten Checkout, Python 3.11+; keine zusätzlichen Laufzeitpakete:

```powershell
New-Item -ItemType Directory -Path private -Force
python scripts/maxxicharge_fixture.py --output private/synthetic-input.json
$env:PYTHONPATH = 'src'
python -m ems_maxxicharge --input private/synthetic-input.json --config simulator/config.example.json --output private/new-run
```

`--output` muss ein **neues** Verzeichnis unter einem existierenden Elternordner
sein. Keine vorhandenen Reports überschreiben. Erst nach erfolgreicher Berechnung
entstehen `simulation.json`, `index.html`, `normalized-input.json`, `mqtt-sim.jsonl`.
`manifest.json` mit SHA256 und `complete=true` wird zuletzt geschrieben. Nur
vollständige Verzeichnisse verwenden. Gleiche Eingaben/Konfiguration erzeugen
bei gleicher Code-/Python-Version dieselben Artefaktbytes; keine wall-clock-Zeit
oder Zufallszahlen in der Rechnung. Codehash, Python-Version und eine an Code,
Eingaben und Konfiguration gebundene `run_id` werden im Ergebnis gespeichert.

Kontext für eine einzige gespeicherte EOS-Referenzfläche vorbereiten:

```powershell
python scripts/maxxicharge_context.py --eos-config PRIVATE_SAVED_CONFIG.json --output private/context.json --pv-conversion-factor 0.95 --acknowledge-proxy --acknowledge-load-scope-assumption
python -m ems_maxxicharge --input PRIVATE_SAVED_SOLUTION.json --input-kind eos --context private/context.json --config simulator/config.example.json --output private/new-historical-run
```

0,95 ist hier eine **Beispielannahme**, keine automatische Bestätigung des
PV-Messpunkts. Der Kontextgenerator übernimmt nur Standort/Geometrie und den
Quellhash, keine Zugangsdaten. Er lehnt mehrere Referenzflächen ab, statt deren
unterschiedliche Ausrichtungen zu mitteln. Private Dateien bleiben unter `private/`.

## Docker-Service

```sh
docker build --network none --pull=false -f simulator/Dockerfile -t ems-maxxicharge-simulator:poc-local .
```

Das Image enthält nur Simulator und drei reine Dashboard-/Messvertragsmodule;
keinen produktiven Sync-/evcc-/Gerätecode. Dedizierte Build-Allowlist verhindert,
dass private Daten oder Tokens in den Build-Kontext gelangen. Python-Basisimage
ist per Digest gepinnt. Der Code benötigt zur Laufzeit keine Netzwerkpakete.

Für Compose ausschließlich einen neuen SIM-Eingangsordner (`input.json`,
`config.json`) und einen disjunkten neuen Output-Elternordner vorbereiten.
`SIM_INPUT_DIR` und `SIM_OUTPUT_DIR` explizit setzen. UID/GID 10001 muss im
dedizierten Output schreiben dürfen; **keine** Rechte bestehender EMS-Verzeichnisse ändern.

```sh
docker compose -f simulator/compose.yaml config
docker compose -f simulator/compose.yaml run --rm --no-deps ems-maxxicharge-simulator
```

Offline-Netzwerk `none`, unprivilegierte UID, Root-FS read-only, Eingang read-only,
separater Ausgang, keine Ports, Geräte, Secrets, Docker-Socket oder Abhängigkeit
zu produktiven Containern, kein Autostart. Ein erneuter Lauf benötigt ein neues
Output-Elternverzeichnis. Das Produktiv-Compose bleibt unverändert.
[Docker-Netzwerkreferenz](https://docs.docker.com/reference/compose-file/services/#network_mode).

## Dashboard und Wirtschaftlichkeit

Die erzeugte `index.html` ist eine lokale Vorschau des vorhandenen Dashboards
mit SIM-Panel, vier Szenarien, Intervallschieber, PV-Leistungen, SOC,
PV-/Netzladung, Entladung, Netzbezug/-einspeisung und kumulierter Kostendifferenz.
Keine externen Assets, Browserabfragen oder Steuerknöpfe. Ohne SIM-Report ist die
bisherige HTML-Ausgabe bytegleich. Der bestehende Datei-Reader akzeptiert optional
`--maxxicharge-sim /PRIVATE/run/simulation.json`; er zeigt nur an und simuliert nie.
Der bestehende produktive Publisher bekommt in diesem Auftrag keine neue Option,
keinen Zeitplan und keinen neuen Mount. Der lokale Prüfsummen-Pin wird für das
erweiterte Lesepaket konsistent aktualisiert, ohne Ausführung auf Unraid.

Verglichen werden zusätzlich an Last gelieferte PV-Energie, Netzbezug,
Einspeisung, Verluste, Stromkosten, Einspeiseerlöse, optionale Verschleißkosten und
Investition. Gespeicherte Energie zählt erst bei Abgabe an die Last als
PV-Eigenverbrauch; Speicherverluste zählen nicht als Eigenverbrauch. Netzladung
erzeugt keine PV-Eigenverbrauchsmenge.

`savings_cash_eur` = Kosten Bestand − Kosten Szenario, im betrachteten Zeitraum.
`savings_inventory_adjusted_eur` berücksichtigt zusätzlich die Änderung nutzbarer
Endenergie gegenüber Anfangsenergie, bewertet für alle Speicher mit demselben
konfigurierten EUR/kWh-AC-Wert. Dadurch bleibt ein anderer End-SOC sichtbar und
initiale Zusatzenergie wird nicht als gratis erzeugte PV gewertet. Beide Zahlen
sind SIM. Netzbezugskosten enthalten keine festen Grundgebühren.

`investments_eur` und `annual_maintenance_eur` sind nach Szenario konfigurierbare
Zusatzinvestitionen/-kosten. Fehlende Werte sind `null` / „Nicht hinterlegt“, nicht
0 EUR. Keine erfundenen Hardwarepreise. `horizon_savings_minus_investment_eur`
zeigt bei hinterlegtem CAPEX die Zeitraumdifferenz nach Investition.

Jahresersparnis/Amortisation bleiben unbekannt, bis **mindestens 8.760 lückenlose
gemessene Stunden**, `representative_year_confirmed=true` und Wartungskosten
vorliegen. Dann: endwertbereinigte Ersparnis × 8.760 / Stunden − Jahreswartung;
einfache Amortisation = Investition / positiver Jahresersparnis. Keine Zinsen,
Degradation, Ersatzinvestitionen oder Tarifentwicklung; kein Finanzierungsmodell.
Ein kurzer alter Prognoselauf wird nicht auf ein Jahr hochgerechnet.

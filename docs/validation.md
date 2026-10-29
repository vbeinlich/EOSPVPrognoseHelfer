# Validierung — 28.10.2026

## Findings-Korrekturen — 29.10.2026

Aktueller Umfang: 168 Tests mit gepinntem EOS; ohne EOS 164 Tests und zwei explizit
übersprungene Integrationstestdateien. Neue Prüffälle und verbleibende Abnahme sind in
[FINDINGS_ISSUE_1.md](FINDINGS_ISSUE_1.md) dokumentiert. Die folgenden Abschnitte bewahren
die ursprünglichen Ergebnisse; deren Zählstände und damalige Providerkonfiguration sind
historisch und keine Behauptung über den heutigen Anlagenstand.

- Dynamische PV-Präfixe, Mindestlücke bei 23 h, Grenze bei 24/30,25/37/47,75 h,
  vollständige Solar-Nachtintervalle, Sommer-/Winterzeit und 15/30/60-Minuten-Quellkadenzen.
- Cache-TTL, parallel wartende native Leser, fehlgeschlagene Abrufe und Neustart-Cooldown;
  wiederholte App-Zyklen ohne EOS-Schreiben; nativer innerer EOS-Cache wird nur bei fälligem
  gesperrtem Helferabruf umgangen. Langsamer Abruf über eine Viertelstundengrenze richtet
  den zukünftigen Horizont danach neu aus.
- Reale EOS-API-Importe im isolierten Test: 37-h-PV-Präfix, historisch begrenzter Preis-GET
  und explizit vollständig rückgelesene 192 Preise; fehlende Zukunft bleibt Fehler.
- evcc-HTTP-Testserver mit selektiertem Batterie-Gerät, konservativ belegtem ungecachtem
  Geräte-Lesefenster und fehlgeschlagenem Folgelesen; frischer unveränderter SoC, mehrere
  Geräte, unbekannte Treiber/Versionen, Cacheantwort, Fehler, fehlende Werte und Neustart.
- Native GENETIC-Auflösung und Optimierung mit 24 h Kontrolle plus tatsächlich gedecktem
  Tail; ältere gespeicherte PV-Tailpunkte werden durch echte begrenzte Runtime-Preise
  ausgeschlossen. Keine historischen PV-Platzhalter.
- Lesende Produktionsprüfung: EOS PREDICTION/PVForecastImport/ElecPriceImport,
  48 h Prognose, 24 h Kontrolle; evcc 0.318.1. Geschützte Geräte-GETs ohne vorhandenen
  Key HTTP 401; neuer Adapter bestätigt `accepted=false`, `source_timestamp=null`.
  Kein produktiver Import, keine Optimierung, kein echter Forecast.Solar-Abruf.

## Erweiterungen aus Issue #1

- 98 Tests mit gepinntem EOS-Quellbaum erfolgreich; ohne EOS 95 Tests und eine explizit
  übersprungene Integrationstestdatei. Ruff ohne Befunde.
- Neues echtes EOS-HTTP-Integrationstest-Szenario im Container ohne Netzwerk:
  PV-/Last-/Einspeisetarifimport, HA-SoC-Konvertierung 55,5 % → 0,555 via
  `/v1/measurement/value` mit Roh-Rücklesung; evcc-Endkundenpreise einschließlich
  negativer Preise in `ElecPriceImport`; anschließend 24-h-GENETIC-Lauf über
  POST `/v1/optimize` mit 3.600-s-Slots und frischem Anfangs-SoC.
- Aktiver nativer `ElecFeeFixed` mit 0,1138655 EUR/kWh und 19 % wird dabei aktualisiert.
  Positiver und negativer Importpreis bleiben auch nach nativen Providerupdates und
  Simulation exakt unverändert; Gebührenkonfiguration und EMS-Modus bleiben erhalten.
- Neue Tests prüfen SoC-Grenzen/Quellalter, unknown/unavailable, DST-Liefertage
  (92/96/100 Intervalle), Preis-/Lastlücken, 24-h-Kontrollhorizont und begrenzten Tail,
  persistente Idempotenz/Preisrevisionen, Timeout-/Speicherfehler, getrennte Opt-ins,
  DRY_RUN-Standard und Sperren bei Geräteadaptern/Webhooks/fremden Providern.
- Frische HA-Meldungen während eines laufenden Zyklus werden gegen die Uhrzeit nach
  dem Lesen geprüft. Während der Vorprüfung veraltender SoC verhindert den POST.
- Zwei parallel gestartete Helferprozesse mit derselben Statusablage erzeugen zusammen
  genau einen POST; beide sehen anschließend denselben erfolgreichen Ereignisstatus.
- Vorhandenen privaten evcc-Snapshot ohne neue Netzwerkabfrage mit dem neuen Parser
  geprüft: 192 gültige Viertelstunden, 27.10.2026 23:00 UTC bis 29.10.2026 22:45 UTC,
  vollständiger nächster Liefertag 29.10.2026 mit 96 Intervallen erkannt. Dies bestätigt
  das Datenformat, ersetzt aber keine LUOX-Endpreisabnahme oder EOS-Schreibfreigabe.
- Installiertes OpenAPI und laufende EOS-/evcc-Konfiguration ausschließlich lesend
  geprüft. EOS-Preisprovider ist weiterhin `ElecPriceEnergyCharts`; der Live-Preisimport
  wird bis zur separaten Umstellungsfreigabe blockiert. Kein HA-Token veröffentlicht.

Die folgenden Angaben dokumentieren zusätzlich die ursprüngliche PV-Validierung.

## Lokal erfolgreich ausgeführt

- Ruff: keine Befunde in `src` und `tests`.
- 44 Tests mit vorhandenem EOS-Quellbaum erfolgreich, darunter zwei echte EOS-Integrationstests.
- Ohne optionales EOS-Paket: 42 Tests erfolgreich, Integration explizit übersprungen.
- EOS-Integration auf Commit `8a8cd43a1915668927eda5504b7de039c2e762b4`, ohne Netzwerk:
  normalisierte synthetische PV-Daten in `PVForecastImport` importiert, rohe Reihe über
  `bounded_forecast_array` zurückgelesen und exakt verglichen; 48-h-GENETIC-Lauf mit
  synthetischer Batterie, 900-s-Slots, 192 Entscheidungen und endlichen Kosten erfolgreich.
- Native Forecast.Solar-Implementierung mit abgefangenem HTTP getestet: ein Aufruf für
  eine PV-Fläche, korrekte Übernahme der Testparameter und native Azimutumrechnung.
- Docker-Build `eos-source` erfolgreich.
- Container-Smoke-Test als nicht-root, read-only, ohne Netzwerk und mit entfernten
  Capabilities: Dry-run mit synthetischen Tagesdaten erzeugte 192 Intervalle,
  80 Quellpunkte und 112 Nachtfüllungen. Anschließender Healthcheck Exitcode 0.
- `docker compose config --no-path-resolution` und `git diff --check` erfolgreich.

Das sind lokale Tests. Sie belegen weder eine aktuelle echte Forecast.Solar-Prognose noch
eine Abnahme auf dem Unraid-Server. Die vorhandene Installation wurde nur per GET gelesen;
es gab keinen externen Forecast.Solar-Abruf und keinen produktiven EOS-Schreibzugriff.

## Reproduzieren

```sh
docker build -f tests/integration/Dockerfile -t eos-pv-helper:eos-test .
docker run --rm --network none eos-pv-helper:eos-test
```

Der EOS-Quellbaum wird im Testimage explizit auf PYTHONPATH gelegt: das untersuchte
Upstream-Wheel enthält nur das Rootpaket, nicht alle benötigten Unterpakete.
Damit wird nicht versehentlich eine andere PyPI-Version getestet.

## Noch erforderlich, Issue bleibt offen

1. Vorhandene echte Forecast.Solar-Rohdaten/Export prüfen oder nach ausdrücklicher
   Zustimmung einen einzelnen nativen Abruf ausführen; keine parallelen Clients.
2. Tatsächliche Quellkadenz und verfügbaren Horizont nachweisen. Die berichteten
   26 Stundenwerte dürfen nicht als 48-h-Abdeckung ausgegeben werden.
3. Neuen Helfer auf Unraid im Dry-run testen; keine bestehenden Container verändern.
4. Erst nach ausdrücklicher EOS-Schreibfreigabe importieren und roh zurücklesen.
5. Separat freigegebenen EOS-Optimierungslauf mit genau dieser echten Reihe nachweisen;
   frische Messwerte, Last und Preise müssen unabhängig ebenfalls gültig sein.
6. Ergebnisse mit Zeitstempeln dokumentieren und erst danach Issue #1 schließen.

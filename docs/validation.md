# Validierung — 28.10.2026

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

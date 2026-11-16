# Phase 2 – Abnahmebericht vom 16.11.2026

**Technische Offline-Abnahme bestanden. Historische Wirtschaftlichkeitsabnahme
offen: die Original-CSV ist nicht zugänglich.** Es gibt keine aus Messdaten
belegten neuen Szenariozahlen und keine Jahresamortisation. Keine
Produktivinstallation, Gerätebefehle, Registry-Veröffentlichung oder Merge.

## Bestand und Umsetzung

Die Phase-1-Grundlage ist als Commit `a4251a6` erhalten. Sie hatte vier Szenarien,
825 Tests ohne die drei markierten GENETIC-Tests und zwei Oktober-Prognosereplays.
Das fünfte Szenario und die 120-h-HA-Auswertung waren dort nicht implementiert.
Vorhandene Physik/PV-Modelle/Renderer wurden erweitert und weiterverwendet.

Jetzt: sieben Ausbaukonfigurationen, 13 Standardvergleichszeilen mit A/B/C,
22 bei explizit optionaler Netzladeannahme. Bestätigte Herstellerfähigkeiten und
unbestätigte Firmware-/Smart-Meter-/Netzladeannahmen sind getrennt dokumentiert.
Modell B schreibt nur lokale Grenznachrichten; A/C nur lokale Telemetrie.
Der Altmodus ist ausdrücklich theoretisch gekennzeichnet und bleibt kompatibel.

## Tatsächliche November-Referenz: nur Betreiberangabe

| 10.–14.11.2026, 120 Stunden | Mitgeteilter Wert | Unabhängig reimportiert |
| --- | ---: | --- |
| Gesamtverbrauch | ca. 227,88 kWh | Nein |
| Bestands-PV | 64,10 kWh | Nein |
| Netzbezug | 168,23 kWh | Nein |
| LUOX-Netzbezugskosten | ca. 67,17 EUR | Nein |
| Gleicher Bezug zu 0,32 EUR/kWh | ca. 53,83 EUR | Rechnerisch 53,8336 EUR; Stundenbelege fehlen |

Nicht gefundene CSV, fehlender lesender HA-Zugang und der benötigte Importvertrag
sind im [Runbook](MAXXICHARGE_PHASE2_RUNBOOK.md) dokumentiert. Die Tage 8./9.11.
werden ausgeschlossen. Die Aggregate ersetzen keine Originalstunden, keine
Einspeisemengen, Lade-/Entladeflüsse, SOC-Grenzen oder zeitlich zugeordneten Preise.

| SIM-Vergleichszeile | Historisches Ergebnis | Investitionsannahme |
| --- | --- | --- |
| Bestand 11 kWp +13 kWh E3/DC | Offen, CSV fehlt | 0 EUR Zusatzinvestition |
| +2 kWp ohne Zusatzspeicher | Offen, CSV fehlt | Separat konfigurierbar, unbekannt |
| +2 kWp +5 kWh, A autonom | Offen, CSV fehlt | 2.500 EUR |
| +2 kWp +5 kWh, B Grenzen | Offen, CSV fehlt | 2.500 EUR |
| +2 kWp +5 kWh, C ideal | Offen, CSV fehlt | 2.500 EUR |
| +3 kWp ohne Zusatzspeicher | Offen, CSV fehlt | PV-only +3-kWp-Mehrkosten, unbekannt |
| +3 kWp +5 kWh, A autonom | Offen, CSV fehlt | 2.500 EUR + unbekannte Mehrkosten |
| +3 kWp +5 kWh, B Grenzen | Offen, CSV fehlt | 2.500 EUR + unbekannte Mehrkosten |
| +3 kWp +5 kWh, C ideal | Offen, CSV fehlt | 2.500 EUR + unbekannte Mehrkosten |
| +6 kWp ohne Zusatzspeicher | Offen, CSV fehlt | Separat konfigurierbar, unbekannt |
| +6 kWp +10 kWh, A autonom | Offen, CSV fehlt | Separat konfigurierbar, unbekannt |
| +6 kWp +10 kWh, B Grenzen | Offen, CSV fehlt | Separat konfigurierbar, unbekannt |
| +6 kWp +10 kWh, C ideal | Offen, CSV fehlt | Separat konfigurierbar, unbekannt |

Erst ein erfolgreicher Originalimport liefert für diese Zeilen PV/Eigenverbrauch,
Bezug/Einspeisung, Verluste, SOC, LUOX-/Festpreis-/Nettokosten und Speichermehrwert.
Die Tabellen des Dashboards zeigen Cashflow und endwertbereinigte Ersparnis
getrennt. Unbekannte Investition ist kein kostenloser Ausbau.

## Ausgeführte Prüfungen

- **853 Tests bestanden** in 82,65 Sekunden: sämtliche vorhandenen und neuen
  Tests, einschließlich der drei `genetic_execution`-Tests. Docker-Testumgebung
  `eos-replay-worker:review-test`, Python 3.11.18, kein Netzwerk, read-only
  Projektmount/Root, temporäres `/tmp`, ein Solver-/BLAS-Thread. Kein Markerfilter.
  25 neue Tests gegenüber Phase 1, darunter ein vollständiger CSV→13-Szenarien→
  HTML/Manifest-Lauf mit ausdrücklich synthetischem 120-h-Datensatz.
- `ruff check --no-cache src tests scripts`, `git diff --check`, Dashboard-/LAN-
  Hashprüfungen, Evidence-Embedding- und Replay-Worker-Inventarprüfung bestanden.
  Der unabhängige `review/pr22_contract_probe.py` meldet beide Gegenbeispiele PASS.
- Physiktests prüfen unabhängige Standortbilanzen einschließlich gespeicherter
  Anfangs-/Endenergie, Lade-/Entladeverluste, gemeinsame Maxxi-AC-Grenze,
  Abregelung, SOC-Grenzen, keine gleichzeitigen Richtungen im Idealmodell,
  Reglerüberschwingen in A und die getrennten Herkunftspools.
- Hersteller-/Adaptertests verwerfen genaue Hardware-Sollwertbehauptungen;
  optionale Netzladung erzeugt eigene neun Varianten. Kosten-/Speichermehrwerttests
  kontrollieren gleichen PV-Ausbau und passende E3/DC-Vergleichssteuerung.
- Historische Negativtests verwerfen Lücken, Duplikate, W statt Wh, Zählerstände,
  fehlende Werte, falsche SOC-Zeiten, inkonsistente Messgrenzen, unbekannte
  Tarifaggregation, NaN und abweichende November-Referenzsummen. Warnungen führen
  nicht zu bestandener historischer Abnahme. Wirkungsgrad-Fit wird nicht angewandt.
- Offline-Dockerbuild aus hash-gepinnten, separat vorbereiteten Wheels erfolgreich.
  Build-Netzwerk bleibt `none`; kein Download im Build oder im laufenden Service.
- Finales Image zweimal mit identischen **synthetischen 120 Stunden im Juni**
  ausgeführt, zusätzlich alter Vier-Szenarien-Modus. Keine dieser Zahlen sind
  November-Messdaten. UID 10001, Root/Input read-only, `cap_drop=ALL`,
  `no-new-privileges`, 384 MiB, 0,5 CPU, PID-Limit 32, Netzwerk `none`, keine
  Ports/Geräte/Secrets/Produktionsmounts, Eingangsprüfsummen unverändert.
- In diesem synthetischen Lauf maximaler Standortbilanzfehler
  `1,31e-9 Wh`; gemeinsamer AC-Ausgang maximal `800 W` bis auf Rundungsfehler.
  Alle drei Idealmodelle mit bewiesenem MILP-Optimum abgeschlossen.
  Zwei Läufe ergaben bytegleiche vollständige Manifeste und Artefaktprüfsummen.
- Headless Edge: neuer 13-Zeilen- und alter Vier-Zeilen-Report bestanden;
  Szenariowechsel A/B/C, Schieber, Kosten/SOC/PV, Desktop 1365 px und Mobil 390 px,
  keine JavaScript-Fehler oder externen Netzwerkanfragen. Screenshot visuell geprüft.
- Ohne SIM-Bericht HTML bytegleich zum eingefrorenen Basiscommit
  `546baa63ade70cab20c67a7410575c8d2b8dc667`. Produktionssteuerung, Root-Compose,
  produktive Konfiguration und Aktivierungsgates stimmen mit
  `simulator/production-baseline.json` überein. Nur der lokale Dashboard-Bundle-
  Prüfsummenpin wurde angepasst; Publisher nicht auf Unraid ausgeführt.

### Identität der lokalen synthetischen Prüfartefakte

```text
Image: sha256:a1ede9bf1a37ff4225deb8c2a1c49b7d746c741c2b8ce2df14c2bf627bec5fb7
Run: eb7a4a726d2368cc4c9ee6c577c9a7c2bd8869c4d30649a7fe0e1a4cdb2fef05
Engine: c4fb96bbfb6a1ee713b4918443cd325038212e5b4734382facda37dadede3f7f
Input: 7d1b33aac4ac777c428517bc5a94fa45956b4647788628fa04a866bc43e5c391
Config: 503f45946d26de7839bcb984ccf7850d56f34e8a815990b58138d6c070f655cd
Manifest: 0fb66bdb9904510c2a4be9c7160a9b91588044eb62abed27fb58a56baa310f6a
Default HTML: 781958eaa1c55e8b2bddb763cacb7db05932944bce640ec01ca9f9b7fa530765
Dashboard bundle: 73e705dad32a672afd5947c508dd2b0e29406f25da4bdcfc96d8e39f7ff8004f
```

Lokale Logs/HTML/Screenshots liegen ignoriert unter `private/phase2-*`; keine
Originalmessungen, Zugangsdaten oder Wheelbinärdateien werden eingecheckt.
Reproduzierbare synthetische Eingabe:

```powershell
python scripts/maxxicharge_fixture.py --days 5 --seconds 3600 --output private/synthetic-120h.json
```

Für die verwendete Config eine unveränderte private Kopie von
`simulator/phase2.example.json` verwenden; Container-/Browserprüfer:
`scripts/maxxicharge_container_smoke.py --phase2` und
`scripts/maxxicharge_ui_smoke.mjs --phase2`. Startdetails im Runbook.

## Verbleibende Abnahme

1. Original-CSV und belegte Messgrenzen/SOC-Zeitpunkte/LUOX-Preisaggregation
   bereitstellen, lesend importieren und auditieren; ggf. E3/DC-Wirkungsgrade
   korrigieren und Warnungen auflösen. Danach echte 13-Zeilen-November-Auswertung.
2. Eigene Südhütte-/Südzaun-Geometrie bzw. vorhandene Wetter-/Prognosearchive und
   Bifazialitätsannahmen bestätigen. Neue PV-Erträge bleiben stets SIM.
3. Konkrete Firmwaregrenzen/MQTT-Mapping, kompatibles Hausanschluss-Meter und
   eventuelle E3/DC-Koordination belegen. Der inexogy-Zähler ist nicht automatisch
   ein kompatibler Maxxi-Regelzähler. Externer AC-Lade-Start/Stopp bleibt offen.
4. Angebote für PV-only, 3-kWp-Mehrkosten und 6-kWp-Topologie/Kosten ergänzen.
   Fünf Novembertage erlauben keine belastbare Jahresamortisation.

GitHub-CI ist von diesen lokalen Ergebnissen getrennt. Der Draft-PR bleibt ohne
Merge und ohne Produktivaktivierung; historische Abnahme ist ausdrücklich offen.

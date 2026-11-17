# MaxxiCharge Multi-Battery PoC – Bestand und Implementierungsplan

Stand: 15.11.2026. Arbeitszweig `feat/maxxicharge-simulator`, Basis
`546baa63ade70cab20c67a7410575c8d2b8dc667` (EMS v1.1 Evidence Writer).
Dieser Plan wurde vor der Implementierung angelegt.

## Bestandsanalyse

- Python 3.11+, `eos_pv_helper`: PV-Normalisierung, SoC-/Tarifimport, bestehender
  Sync-/GENETIC-Pfad. Produktiver Helfer ist ein eigener Container mit expliziten
  Schreibfreigaben. `app.py`, `sync.py`, Konfiguration und produktives Compose
  werden für den PoC nicht geändert.
- PV stammt aus dem vorhandenen nativen EOS-Forecast.Solar-Pfad, mit zentralem
  Cache/TTL/Lock. Tarife stammen aus evcc, Messwerte aus E3/DC/evcc/HA. Kein neuer
  Wetter-, Tarif-, E3/DC- oder HA-Poller im Simulator.
- `replay-worker/` arbeitet bereits offline. `dashboard.py` und
  `dashboard_view.py` erzeugen statisches HTML aus Archiven. Ein getrennter
  Nginx-Container (`deploy/dashboard/`) liefert diese Dateien aus. Bestehende
  Dateien, Publisher-Jobs, Ports und Container werden nicht umkonfiguriert.
- Lokal vorhandene native Solver-Antworten vom 29./31.10.2026 ermöglichen
  reproduzierbare Prognose-Replays. Das vorhandene historische Inventar
  (`HISTORICAL_ACTUALS_INVENTORY.md`) weist noch keinen vollständigen Export
  gemessener Standort-Intervallenergien nach. Ledger-Herkunftsbuchungen und
  Solver-Prognosen werden nicht als gemessene Verbrauchshistorie umetikettiert.
- Docker Desktop ist lokal erreichbar; lokale EMS-Testimages sind vorhanden.
  Die laufenden lokalen Container gehören anderen Anwendungen. Eine aktuelle
  NAS-Containerinventur wird nur lesend versucht; alte Bestandsnachweise werden
  nicht als heutiger Live-Status ausgegeben.

## Umsetzung in dieser Reihenfolge

1. Strikter Offline-Datenvertrag mit UTC-Intervallen, Wh, finalen EUR/kWh,
   Herkunft/Hashes, Datenart und vollständiger Abdeckung. Adapter für gespeicherte
   EOS-Prognosen und den vorhandenen Messdatenvertrag; kein Backfill.
2. Separates Paket `ems_maxxicharge`, konfigurierbarer Batteriesimulator mit
   internem Wh-Zustand, Leistungs-/SoC-Grenzen, getrennten PV-/Netz-Ladeflüssen
   und 92 % Wirkungsgrad je Richtung als expliziter Annahme.
3. Südhütte/Südzaun mit 1 kWp, Azimut 180° (Nord=0°), Neigung 14°/90°.
   Wiederverwendung vorhandener flächenspezifischer Prognosen oder vorhandener
   Strahlungsdaten; aggregierte Bestands-PV allein beweist keine neue Ausrichtung.
   Ein expliziter geometrischer Proxy darf nur als Sensitivitätsannahme erscheinen.
   Bifazialer Zuschlag und Verluste sind konfigurierbare Annahmen.
4. Deterministische Koordination auf gemeinsamer Standortbilanz: eigene Zusatz-PV
   zuerst nutzen/speichern, E3/DC für den Rest; kein Batterieexport zur Ladung der
   jeweils anderen Batterie, keine gleichzeitige Ladung/Entladung. Preisladung
   nur nach Verlusten und Kostenprüfung mit begrenztem Vorschauhorizont.
5. Vier Szenarien mit identischen Eingaben/Bestandsparametern, getrennten
   Flussbilanzen, Kosten, zusätzlichem PV-Eigenverbrauch, Bezug, Einspeisung,
   Verlusten, Investition und transparenten Endenergien/Endwerten. Kein
   Amortisationsversprechen aus einem kurzen Prognosehorizont.
6. Brokerfreies Adapter-Interface und lokales MQTT-Nachrichtenjournal ausschließlich
   im SIM-Namensraum. Dokumentierter Vertrag, keine erfundenen MaxxiCharge-Topics
   und kein implementierter Hardwaretransport.
7. Optionales SIM-Panel im vorhandenen Dashboard, standardmäßig ohne Daten;
   Simulator erzeugt eine getrennte Vorschau mit Szenariowahl und Intervallansicht.
   Produktiver Publisher und Nginx bleiben unverändert.
8. Eigene Docker-Datei/Compose mit `network_mode: none`, RO-Eingaben, separatem
   Output, ohne Secrets/Socket/Geräte, unprivilegiert und ohne Autostart.
9. Analytische Bilanz-/Grenzwert-/Preis-/Herkunftstests, randomisierte Langläufe,
   Adapter-/Dashboard-/Isolationsprüfungen und lokale Docker-Smokes. Private
   historische Prognose-Replays samt SHA256; reale Messdatenabnahme nur mit
   tatsächlich vorhandenem vollständigem Export.

## Abnahme und Grenzen

Kein Deploy auf Unraid, kein Push, keine Freigabe oder Aktivierung von realer
Speichersteuerung. SIM gilt für alle neuen Resultate. Hardware-Ladegrenzen,
Investitionsangebote und genaue MQTT-Gerätebelegung bleiben explizite Parameter
bzw. noch zu belegende Verträge. Die Abnahme dokumentiert ausgeführte Tests und
fehlende Daten getrennt. Es wird keine Vollständigkeit einer Messdatenhistorie
behauptet, die nicht vorliegt.

# MaxxiCharge: interner Adaptervertrag v1

**SIM, kein Hardwareprotokoll.** Es sind weder MaxxiCharge-Hersteller-Topics noch
Schreibmöglichkeiten des V2 Plus nachgewiesen. Dieses Dokument definiert die
interne EMS-Schnittstelle, auf die eine spätere geprüfte Geräteanbindung abbilden
kann. Im PoC existiert kein MQTT-Client, Brokerzugriff, Gerätepasswort oder
schaltbarer Realmodus. `mqtt-sim.jsonl` ist ausschließlich eine lokale Datei.

## Grenze zwischen Modell und Transport

`ems_maxxicharge.adapter.BatteryAdapter` beschreibt `apply_intent(Intent)` und
`read_telemetry()`. `SimulationAdapter` validiert Leistung/Zeiten und liefert
lokale Nachrichtenhüllen. Das physikalische Offline-Modell bleibt in `battery.py`,
die Standortkoordination in `engine.py`; beide benötigen keinen Transport.
Ein künftiger realer Adapter liefert dieselben kanonischen Telemetriefelder und
übersetzt Intents in dann belegte Gerätebefehle. Hersteller-Mapping, Live-Regelkreis
und Freigabegate sind ausdrücklich noch nicht implementiert.

Ein späterer Hardwarewechsel soll dieses Interface implementieren, nicht die
Energie-/Preisbilanz neu erfinden. Der Offline-Szenarienrechner bleibt ein
Offline-Rechner; ein Replay historischer Intents wird niemals zum Live-Regler.

## Simulierter Namensraum

```text
ems/sim/maxxicharge/v1/<run-id>/<scenario>/intent
ems/sim/maxxicharge/v1/<run-id>/<scenario>/telemetry
```

`scenario`: `pv2_bat5` oder `pv6_bat10`. Die `run_id` bindet normalisierte Eingaben,
Konfiguration und Simulator-Codehash. Unterschiedliche Konfigurationen erhalten
unterschiedliche IDs. Jeder Lauf gehört in ein getrenntes Ergebnisverzeichnis.
Diese Topics werden **nicht publiziert**. Hülle: `transport=local_journal_only`,
`qos=0`, `retain=false`, Payload immer `schema_version=1`, `mode=SIM`.

Beispiel-Intent (alle Leistungen positiv, Richtungen getrennt):

```json
{
  "schema_version": 1,
  "mode": "SIM",
  "command_id": "12",
  "at_utc": "2026-06-18T03:00:00+00:00",
  "valid_until_utc": "2026-06-18T03:15:00+00:00",
  "discharge_w": 0,
  "grid_charge_w": 400,
  "accepted_in_simulation": true
}
```

`accepted_in_simulation` bestätigt nur die lokale Modellannahme. Es ist keine
Gerätequittung und kein Ausführungs- oder Messnachweis. Netzladung und Entladung
dürfen nicht gleichzeitig positiv sein. Grenzen kommen aus derselben
Simulator-Konfiguration wie das Batteriemodell. Die Simulation verwendet die
Intervallzeit als Uhr; historische Zeitstempel sind **keine** live gültigen Intents.

Telemetrie enthält `start_utc`, `end_utc`, `soc_percent` am Intervallende,
`end_wh` intern sowie mittlere `charge_pv_w`, `charge_grid_w`, `discharge_w`.
Fehlende Zustandswerte werden nicht mit Null ersetzt. Die vollständigen
Energieflüsse, Herkunftspools und Verluste stehen zusätzlich im SIM-Report.

## Anforderungen vor jeder zukünftigen realen Anbindung

- Gerätemodell/Firmware und tatsächliche MQTT-Lese-/Schreib-Topics, Einheiten,
  Vorzeichen, Grenzwerte und AC-/DC-Messpunkte anhand Herstellerunterlagen und
  lesender Telemetrie belegen. Keine Topics aus diesem SIM-Namensraum übernehmen.
- Ein eindeutiger Befehls-Owner und gemeinsames Standort-Meter für beide Speicher.
  Keine konkurrierende Hersteller-/evcc-/HA-Schreibstrecke.
- Eigener freigegebener Real-Namensraum, Broker-ACL, frische Originalmesszeiten,
  monotone Sequenz/Idempotenz, Ablaufzeit, Timeout, Verbindungsverlust/LWT,
  manuelle Übersteuerung und sicherer Rückfall. Keine retained Aktorbefehle.
- Anforderung, Geräte-Ack und unabhängige gemessene Wirkung getrennt behandeln.
  SOC-/Leistungsgrenzen unmittelbar vor Ausführung neu prüfen. Bei veralteter
  Messung keine Blindkompensation zwischen den Speichern.
- Tests und Betreiberfreigabe für reale Befehle sind ein gesonderter Auftrag.
  Der PoC enthält absichtlich keinen Adapter, den man durch eine Konfigurations-
  oder Umgebungsvariable zum Senden realer Befehle umstellen könnte.

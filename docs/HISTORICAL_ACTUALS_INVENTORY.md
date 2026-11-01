# Historische Daten: was tatsächlich verfügbar ist

Lesender Bestand vom 01.11.2026. Private Ergebnisse und Zahlen bleiben außerhalb
GitHub. Keine Messwertdatei, Config, Token oder SQLite-Kopie in diesem Repository.

| Bestand | Tatsächlicher Nachweis | Für Plan-Ist verwendbar? |
| --- | --- | --- |
| Lösungen 29./30./31.10. | Drei Dateinamen mit Größen/Dateizeiten auf NAS sichtbar | Namen/mtime beweisen weder Inhalt noch historische Eingabenvollständigkeit |
| Lokale GET-Antworten 29./31.10. | Originalbytes und Hashes privat vorhanden; native Kosten-/Endenergie-Replays bestanden | Unveränderte Modelleingaben, keine Messwerte und kein vollständiger Claim-/NAS-Byte-Nachweis |
| Lösung 30.10. und Sync-State | Dateiexistenz sichtbar, Lesen über verfügbaren Pfad verweigert | Nicht berechenbar; keine Rekonstruktion aus Nachbartagen |
| `prices.json`, `forecast.json`, `soc.json`, aktuelle Reports | Laufende Dateien werden regelmäßig ersetzt | Keine rückwirkende Quelle für ältere Ereignisse |
| evcc `/api/state` | Cache-GET erreichbar | Momentaufnahme, keine vollständige Historie oder SoC-Frischegarantie |
| HA-Historie/Statistiken | API benötigt Authentisierung; Probe antwortet 401 | Retention, Entity-Einheiten und Zeitabdeckung noch nicht unabhängig gelesen |
| Batterie-/M-TEC-Ledger | SQLite lesbar, Schema/Counts/Zeiträume in kurzer Read-only-Transaktion geprüft | Teilhistorie der Buchführung; keine vollständige Haushalts-/Zählerbilanz |

## Ledgerprüfung und Grenzen

`mtec_battery_ledger.sqlite3` wurde mit SQLite `mode=ro`, `query_only=ON`,
`timeout=0` und einer kurzen Lesetransaktion abgefragt. Vorher Dateiheader und
Skript geprüft: Rollback-Journalformat, kein konfigurierter WAL-Modus. Keine
Schreibverbindung, Migration, Initialisierung, Backup-Operation oder Fremdprozesssteuerung.
Tabellen: `events(id, ts, kind, kwh, eur, note)`,
`layers(id, ts, source, remaining_kwh, remaining_eur)`, `meta(k,v)`.

Vorhanden sind `charge_grid`, `charge_pv`, `battery_output_known/unknown` und
`mtec_battery_known/unknown`, mit Originalzeitpunkten seit dem 30.10. Private
Counts, Zeitbereiche und Summen wurden getrennt gespeichert. Die Datenbank wächst
im normalen Betrieb weiter; Beobachtungszeitpunkte nicht als neue historische Werte ausgeben.

**Wesentliche fachliche Grenze:** Das vorhandene Skript verteilt die Batterie-
Ladeherkunft proportional anhand von Netzbezug, Hauslast und Batterieladeleistung.
M-TEC-Anteile werden ebenfalls proportional zugeteilt. `charge_grid` ist daher
kein Beweis für einen ausgeführten Netzladebefehl oder einen getrennt gemessenen
physikalischen Netz→Batterie-Energiefluss. FIFO-Layer enthalten bekannte und
unbekannte Herkunft; Restbestand ist kein Ersatz für den physikalischen SoC.

Diese Buchungen dürfen weder als vollständige E3/DC-Ist-Energien in den neuen
Messdatenvertrag eingefüllt noch als tatsächlich durch EOS erzielte Ersparnis
ausgegeben werden. LCOS/Abschreibung im EOS-Modell und FIFO-Energieeinstandskosten
sind verschiedene Größen. Keine Initialbestände oder fehlenden Buchungen ergänzen.

## Noch benötigte private Daten

Originale Intervallenergien für PV, vollständigen Hausverbrauch inklusive separat
geführter Verbraucher, Netzbezug/-einspeisung und Batterie-DC-Bus; ursprüngliche
SoC-Punkte; zugehörige finale Viertelstundentarife. Bei HA sind Energie-Statistiken,
Zählerresets, `state_class`, Einheit, Retention und tatsächliche Messpunktabgrenzung
zu bestätigen. W-Verläufe, Tageszähler und Kosten-Tagesstände sind keine fertigen
Intervallenergien. Ein Ausfall der früheren HA-Bridge kann die HA-Historie lückenhaft
machen, obwohl Ledger-Buchungen existieren (siehe #7/#11).

Die neue Offline-Auswertung akzeptiert ausschließlich einen belegten normalisierten
[Messdatenvertrag](PLAN_ACTUAL.md). Ein künftiger read-only Exporter soll vorhandene
HA-/evcc-Daten wiederverwenden; keine zusätzliche Cloudabfrage und kein zweiter
E3/DC-Poller. Ohne authentisierten privaten Export bleibt die vollständige
historische Plan-Ist-Abnahme offen. Kein SQL auf HA-Recorderdateien und keine
Live-SQLite-Datei mitsamt ignoriertem WAL als vermeintlich konsistentes Backup kopieren.

[HA-Sensor-/Statistikvertrag](https://contributors.home-assistant.io/core/entities/sensor/)
unterscheidet Momentanmessungen und Energiezähler;
[HA-History-GET](https://contributors.home-assistant.io/core/internals/rest-api/)
liefert vorhandene State-Historie, erzeugt aber keine fehlenden Messungen.

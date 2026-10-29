# Issue #1: PV-Horizont, automatische Aktualisierung, Preise und SoC

Stand: 29.10.2026. Umsetzung im bestehenden PR #3. Produktionssysteme wurden nur per GET
gelesen. Keine Änderungen an EOS, evcc, Home Assistant oder E3/DC; keine produktiven
Imports oder Optimierungsläufe. Die unten beschriebenen Schreibtests liefen ausschließlich
mit synthetischen Daten gegen einen isolierten EOS-Prozess ohne externes Netzwerk.

## Ergebnis und Grenzen

| Finding | Umsetzung | Verbleibende Abnahme |
| --- | --- | --- |
| Starre 48 h scheitern am fehlenden dritten Morgen | Längster zusammenhängender validierter Horizont, mindestens 24 h, maximal konfigurierter/EOS-Horizont; jede Viertelstunde bis zur ersten echten Tageslücke | Verfügbare Stunden und Endzeit mit aktueller echter Forecast.Solar-Prognose auf Unraid prüfen |
| Regelmäßige PV-Aktualisierung | Vorhandener nativer EOS-Provider, gemeinsame TTL/Dateisperre, persistente Wartefrist nach Fehlern; Cache-only bleibt Standard | Laufenden Abruf nur am Helfer nach Freigabe aktivieren; einen TTL-Wechsel beobachten |
| Historische Preisintervalle fehlen in EOS-GET | Explizites Zeitfenster, getrennte Historien-/Zukunftsprüfung, definierte numerische Toleranz; Kontrolle von 24 h separat | Reale Preis-Rücklesung erst nach gesonderter Schreibfreigabe wiederholen |
| HA-SoC bleibt bei unverändertem Wert alt | evcc als bevorzugte explizit konfigurierte Quelle, genaues Gerät statt aggregiertem SoC, nur mit belastbarem Lesebeleg | Geschützte evcc-Konfigurations-/Status-GETs liefern auf der aktuellen Anlage HTTP 401; Treiber und ungecachter Geräteabruf konnten dort noch nicht bestätigt werden |
| Alter EOS-PV-Rest könnte den Tail verlängern | Aktuell validierte PV-Endzeit begrenzt Vorprüfung und tatsächliche native Laufzeitarrays | Optimierung bleibt bis zur eigenständigen Freigabe aus |

Die letzte echte lesende Konfigurationsprüfung bestätigt `PVForecastImport`,
`ElecPriceImport`, `ems.mode=PREDICTION`, 48 h Prognose, 24 h Kontrollhorizont und
`tail_horizon_hours=48`. evcc meldet `0.318.1`; `battery.devices` enthält keinen
Messzeitstempel. Konkrete private Konfigurationen und Zugangsdaten bleiben außerhalb Git.

## 1. Dynamischer PV-Horizont

In der privaten TOML vorhandene `[horizon]`-Tabelle bearbeiten:

```toml
[horizon]
mode = "dynamic"
minimum_hours = 24
max_hours = 48
```

Ein altes `hours=24` entfernen oder durch `max_hours=48` ersetzen. Ohne `max_hours`
wird das alte `hours` aus Kompatibilitätsgründen als Obergrenze interpretiert. Ein expliziter
`mode="fixed"` bleibt für reproduzierbare feste Testfenster verfügbar.

Start ist der aktuelle UTC-Viertelstundenbeginn. Das Maximum wird beim nativen Provider
zusätzlich durch `EOS prediction.hours` begrenzt. Originalwerte, einschließlich 0 W
tagsüber, bleiben unverändert. Nur bei ausdrücklich deklarierter 30-/60-Minuten-Kadenz
werden Zwischenwerte innerhalb benachbarter nachgewiesener Stützstellen interpoliert.
Fehlende vollständig nächtliche Intervalle werden anhand Sonnenaufgang/-untergang mit
0 W ergänzt. Fehlende Tageswerte werden weder fortgeschrieben noch extrapoliert.

Eine Lücke bei Stunde 23 sperrt den Lauf. Eine erste Lücke bei Stunde 37 liefert 148
gültige Viertelstunden und einen dokumentierten Abbruch. Ein nach dem letzten Quellpunkt
nachgewiesenes Nachtintervall darf weiter mit 0 W ergänzt werden; spätestens der nächste
ungedeckte Tagespunkt begrenzt den Horizont. Es wird kein dritter Prognosetag erfunden.

`report.json` enthält `requested_max_hours`, `configured_max_hours` beim nativen Provider,
`validated_hours`, `minimum_hours`, `first_uncovered_daylight_interval`, `stop_reason`,
`tail_available_hours`, Start/Ende, `source_count`, `interpolated_count`,
`filled_night_count` und die jeweiligen Zeitstempel. `source_fetched_at_utc` ist der letzte
erfolgreiche native Abruf, nicht der letzte Cachezugriff. Bei zu kurzem Horizont bleibt
die frühere Prognosedatei historisch erhalten, `health.json` ist ungültig und die aktuelle
Diagnose steht in `forecast-error.json` bzw. `sync-report.json`. Alte Dateien sind dann
keine neue gültige Prognose.

## 2. Periodische Aktualisierung mit einem nativen Abrufpfad

Sichere Vorgabe bleibt `source.refresh_enabled=false`; ohne `--refresh-source` wird
auch bei `refresh_enabled=true` nicht extern abgerufen. Für nachträglich ausdrücklich
freigegebenen **lesenden** Dauerabruf nur am Helfer:

```toml
[source]
refresh_enabled = true
max_age_seconds = 3600
retry_seconds = 300
```

Weitere Source-Felder aus der vorhandenen TOML beibehalten. Post Arguments in Unraid:
`run --config /app/config.toml --refresh-source`, bei aktivierter SoC-/Preisdiagnose
`sync --config /app/config.toml --refresh-source`. `DRY_RUN=true`, sämtliche
`write_enabled=false` und der GENETIC-Trigger bleiben dabei ausgeschaltet.

PV wird alle `poll_seconds` (Standard 300 s) geprüft, SoC/Preise im `sync`-Modus alle 60 s.
Ein gültiger Rohcache verhindert den erneuten externen Abruf. `load_forecast()` selbst
verriegelt alle Leser und Schreiber über dieselbe `.lock`-Datei und prüft Cache/Uhr erst
nach Erwerb der Sperre. Parallel gestartete Prozesse mit derselben Ablage rufen die
Quelle einmal ab. Unterschiedliche getrennte Ablagen koordinieren sich nicht; nur eine
Helferinstallation betreiben. EOS muss bereits auf `PVForecastImport` stehen, sonst wird
ein zweiter nativer Forecast.Solar-Abrufpfad abgelehnt.

Ein fehlgeschlagener Abruf erneuert weder Zeitstempel noch Inhalt des alten Caches.
Eine private `.attempt.json`-Datei schützt während `retry_seconds` auch nach Neustarts
vor unmittelbaren Wiederholungen. Alte Daten werden dabei nicht als frisch erklärt.
Ein nativer Abruf kann pro konfigurierter PV-Fläche einen Request benötigen. Es wurde
kein zweiter Forecast.Solar-Client und kein Wetter-/Last-Scheduler ergänzt.

Der native EOS-Request besitzt selbst einen 1-h-Dateicache. Ein nach Ablauf der Helfer-TTL
fälliger Abruf umgeht diesen **lokalen** inneren Cache mit dem vom Provider unterstützten
`force_update=True`. So bezeichnet ein neuer `source_fetched_at_utc` tatsächlich einen
neuen erfolgreichen Request und keine umdatierte alte native Cacheantwort. Die gemeinsame
Helfer-TTL und Sperre bleiben davor wirksam; es wird keine EOS-Server-Update-API aufgerufen.

## 3. Preis-Rücklesung und tatsächlicher Kontrollhorizont

Im untersuchten EOS-Code setzt `fastapi_prediction_series_get()` bei fehlendem
`start_datetime` den Start auf `get_prediction().ems_start_datetime` und das Ende auf
das Prognoseende. Das gilt auch bei `processing=raw`. Der Integrationstest belegt:
192 importierte Preisintervalle bleiben gespeichert; beim EMS-Start 12 h nach
Tagesbeginn liefert der unbeschränkte GET nur 144. Ein explizites Start-/Endfenster
liefert wieder alle 192. Die beobachtete fehlende Historie kann also durch die GET-Grenze
entstehen und bedeutet nicht automatisch Verlust beim Import.

Der Helfer gibt jetzt das eingereichte Zeitfenster explizit im GET an. Zusätzlich darf
EOS tatsächlich nicht mehr vorhandene vollständig vergangene Intervalle abschneiden.
Ein laufendes Viertelstundenintervall gilt weiterhin als benötigt. Jeder vorhandene
eingereichte Wert, auch historische und negative Preise, wird verglichen:
`rel_tol=1e-9`, `abs_tol=1e-12 EUR/Wh`. Fehlende laufende oder künftige Slots sowie echte
Abweichungen sperren die Verifikation. Bezug ist die Uhr **vor** dem Import; ein Slot
wird nicht während einer langsamen Rücklesung nachträglich aus der Prüfung gealtert.

`prices.readback` trennt `historical_missing_intervals`, `future_missing_intervals`,
`mismatched_intervals`, Zahl geprüfter Werte und zusätzliche EOS-Punkte.
`prices.control_coverage` meldet unabhängig davon den benötigten 24-h-Kontrollhorizont,
verfügbare zusammenhängende Stunden und den ersten ungedeckten Slot. Ein korrekter
Import heutiger Preise allein belegt nachmittags noch keine 24 zukünftigen Stunden.
Neue Day-Ahead-Preise müssen erst tatsächlich vollständig vorliegen.

## 4. evcc-SoC mit beweisbarer Frische

Konfiguration mit deaktiviertem Import:

```toml
[evcc]
url = "http://EVCC-HOST:7070" # Im privaten Editor ersetzen.
token_file = "/run/secrets/evcc_token" # Nur einen bereits vorhandenen privaten API-Key verwenden.

[soc]
enabled = true
source = "evcc"
device_name = "db:ID" # Exakte eigene Zuordnung aus battery.devices; ID durch Ziffern ersetzen.
freshness = "e3dc-rscp-status"
max_abs_power_w = 20000 # Plausibilitätsgrenze an die eigene geprüfte Anlage anpassen.
max_age_seconds = 300
write_enabled = false
```

Dies sind Auszüge bestehender Tabellen, keine zusätzlich doppelt anzulegenden Tabellen.
Der Helfer erzeugt **keinen** neuen evcc-Key und ändert weder evcc-Konfiguration noch
Batteriemodus. Fehlt ein bestehender verwendbarer Key, endet die Prüfung bei HTTP 401.
Die Datei kann über das optionale Unraid-Templatefeld read-only eingebunden werden;
Alternative: privates `evcc.token_env="EVCC_TOKEN"`. Keine Tokens ins Issue kopieren.

SoC und Preise verwenden denselben `/api/state`-Snapshot pro Zyklus. Ausgewählt wird nur
das genau konfigurierte einzelne `battery.devices[].name`, niemals der aggregierte
`battery.soc` bei mehreren Geräten. SoC muss endlich in 0..100 % liegen, beide Leistungen
müssen numerisch und innerhalb der konfigurierten Plausibilitätsgrenze sein. Globale oder
gerätebezogene Fehler sperren die Übernahme.

**Warum `/api/state` allein nicht genügt:** `Measurement` und `BatteryState` enthalten in
evcc 0.318.1 keinen erfolgreichen Messzeitpunkt. `updateBatteryMeters()` behält bei
SoC-Lesefehlern den alten aggregierten Wert ausdrücklich bei. Auch `historyUpdated`,
fehlende Fehlermeldungen, Wertänderungen und HTTP-Abrufzeit werden daher nicht als
Frischenachweis verwendet.

Der eng begrenzte alternative Nachweis umfasst zwei zusätzliche **GETs zum vorhandenen
evcc**, nicht einen zweiten externen Anbieter:

1. `/api/config/devices/meter/<ID>` muss dieselbe Gerätekennung und einen nativen
   `e3dc-rscp`-Batterietreiber bzw. dessen unverändertes Template bestätigen. Andere
   Treiber, Custom-YAML, Cachekonfigurationen und unbekannte evcc-Versionen werden abgelehnt.
2. `/api/config/devices/meter/db:<ID>/status` muss erfolgreich SoC und Leistung lesen.
   Im geprüften Code ruft dieser Handler den vorhandenen Geräte-Getter auf. Der native
   E3/DC-RSCP-Getter sendet unter Mutex eine echte `EMS_REQ_BAT_SOC`-Anfrage und verwendet
   keinen Wertcache. Kein Batterie-Setter wird durch diesen Statuspfad aufgerufen.
   Die Abfrage ist auf 15 s begrenzt. HTTP-Caches werden nicht als Beleg akzeptiert.
3. Der unmittelbar gelesene SoC muss zum gemeinsamen Snapshot passen; bei inzwischen
   geändertem SoC wartet der Helfer auf den nächsten Zyklus. Die Leistung darf sich ändern,
   ihre Änderung ist selbst kein Frischenachweis.

Für einen so bestätigten **ungecachten** Lesevorgang wird dessen Beginn als konservative
zeitliche Untergrenze verwendet. `timestamp_kind=successful_uncached_device_read_lower_bound`
und `device_timestamp_available=false` machen deutlich, dass keine Geräteuhr übermittelt
wurde. Der reale Lesevorgang liegt innerhalb des dokumentierten Anfragefensters; sein
maximales Alter wird dadurch konservativ begrenzt. Ein HTTP-Abruf gecachter Werte erhält
keinen solchen Zeitstempel. Die 300-s-Grenze gilt beim Import und erneut unmittelbar vor
einem später ausdrücklich genehmigten Simulationsaufruf.

**Aktuelle Einschränkung:** Auf der realen Anlage liefern die geschützten Konfigurations-
und Status-GETs ohne vorhandenen API-Key HTTP 401. Die native RSCP-Zuordnung und der echte
Frischenachweis wurden dort noch nicht erfolgreich abgenommen. `e3dc`/Modbus oder andere
Treiber dürfen nicht mit diesem RSCP-Nachweis freigeschaltet werden. Dafür ist zunächst ein
eigener geprüfter Getter-/Cachevertrag oder ein vom bestehenden Poller bereitgestellter
letzter erfolgreicher SoC-Gerätezeitpunkt erforderlich; keine generische Timestamp-Override-
Option und kein Aufheben der Altersgrenze. Die neuen Negativtests akzeptieren solche Werte
ausdrücklich nicht.

HA bleibt optionaler Vergleich unter `[soc.ha]`. Ein alter oder fehlender HA-Report blockiert
einen belegten evcc-Wert nicht. `source="homeassistant"` ist nur eine ausdrücklich gewählte
Legacy-Quelle mit weiterhin maximal 300 s; es gibt keinen automatischen Fallback.
`sync-report.json` enthält Gerätekennung, Wert, Quellart, Beleg, Anfragefenster, Alter bzw.
Sperrgrund sowie HA `last_reported`/`last_updated`. `soc.json` erhält bei Fehlern
`usable=false`; ein früherer gültiger Wert wird nicht als frisch weitergereicht.

## 5. Kein alter PV-Rest im GENETIC-Tail

EOS-Importe können alte Punkte außerhalb des neu gelieferten PV-Fensters behalten. Die
Vorprüfung begrenzt PV daher auf `report.end_exclusive_utc`. Weil native GENETIC-Arrays
an lokaler Mitternacht beginnen, wird zusätzlich ein echter evcc-Preisarray dieses Tages
als Laufzeiteingabe übergeben, endend am validierten Kontrollhorizont plus tatsächlich
gedecktem Tail. EOS begrenzt alle Laufzeitarrays auf deren gemeinsame kürzeste Länge.
Dadurch werden ältere gespeicherte PV-Punkte im laufenden Plan nicht wieder angehängt.
Es werden keine PV-Tageswerte oder historischen Platzhalter erfunden und keine alten
Produktionsdatensätze gelöscht.

Die dafür nötigen echten Preisintervalle ab lokaler Mitternacht müssen im evcc-Snapshot
vorliegen. Fehlt dieser historische Präfix, wird ein späterer Simulationsaufruf mit dem
ersten fehlenden Zeitpunkt gesperrt. Die Importprüfung selbst darf abgeschnittene EOS-
Historie weiterhin tolerieren. `native_price_slots_from_midnight` dokumentiert das Format.

Bei erstmaligem Start zwischen zwei stündlichen GENETIC-Slotgrenzen kann im EOS-Speicher
noch der Anfang des laufenden Stunden-Slots fehlen: die neue PV-Reihe startet am aktuellen
Viertelstundenbeginn. Auch diese Kontrolllücke wird nicht erfunden. Nach kontinuierlicher
PV-Versorgung bzw. an der nächsten vollständigen Slotgrenze erneut prüfen; eine bis dahin
gesperrte Preisversion wird nicht als ausgeführt markiert.

## 6. Konkreter erneuter Unraid-Test

1. Den neu veröffentlichten und geprüften Digest aus `IMAGE_PUBLICATION.json` verwenden;
   ein früheres Image enthält diese Fixes nicht. **Nur den Helfer** aktualisieren, keine
   zweite Helferinstanz und keine Änderungen an EOS/evcc/HA/E3/DC. Private TOML und `output`
   sichern; `sync-state.json` nicht löschen. Bestehende Aufzeichnungen behalten ihre Claims.
2. GUI `DRY_RUN=true`; alle drei `write_enabled=false`; `trigger.enabled=false` und
   `run_enabled=false`. In `[horizon]` dynamischen Modus 24..48 h konfigurieren. Neue
   Validierungsregeln bzw. geänderte PV-Parameter erzwingen eine neue Prüfung, auch wenn
   `sync-state.json` noch einen kürzlich geprüften älteren Horizont enthält.
3. Cache-only starten. `report.json` bzw. `forecast-error.json`, `health.json` und Logs prüfen.
   Ein abgelaufener Cache muss als abgelaufen erkennbar bleiben. Erst nach separater
   Abruffreigabe den oben beschriebenen TTL-gesteuerten nativen Quellenbetrieb einschalten;
   das ist weiterhin Dry-run ohne EOS-Import.
4. Bei erfolgreicher PV-Prüfung Stunden, Ende, erste ungedeckte Tagesviertelstunde,
   Original-/Interpolations-/Nachtzahlen und echten Quellabrufzeitpunkt notieren. Die
   nächste TTL-Erneuerung beobachten; dazwischen darf kein zusätzlicher nativer Abruf
   entstehen. Für API-Ratenlimits native Logs/Quellprovenienz verwenden, keine zusätzliche
   unabhängige Prognose abfragen.
5. Für Preise `[prices].enabled=true`, Schreiben aus. `[evcc].url` nur einmal pflegen,
   ein altes abweichendes `[prices].url` entfernen. `prices.control_coverage` nach neuer
   Day-Ahead-Veröffentlichung prüfen. Für einen echten erneuten Import/Rohvergleich ist
   **erst eine neue separate Schreibfreigabe nötig**; bis dahin keinen `--write-eos`-Aufruf.
6. evcc-SoC nur mit exakter eigener Gerätezuordnung und vorhandener privater API-Key-Datei
   lesen. Ohne Zugang ist `usable=false`/HTTP 401 das richtige Ergebnis. Nach bestätigtem
   RSCP-Treiber mehrere Zyklen beobachten: unveränderter SoC darf bei jeweils erfolgreichem
   Geräteabruf einen neuen belegten Lesezeitpunkt haben. Fehlerhafte oder fehlende Getter
   dürfen keinen SoC-Import erlauben. Produktionsgeräte für Negativtests nicht abschalten;
   diese Fälle werden bereits lokal synthetisch getestet.
7. `evcc-snapshot.json`, `soc.json` und `sync-report.json` auf Zusammenhang, Beleg und
   Sperrgründe prüfen; optionale HA-Diagnose darf veraltete Reports als solche zeigen.
   Keine Tokens oder vollständigen privaten Quellkonfigurationen veröffentlichen.
8. Ergebnisse mit UTC-Zeitpunkten dokumentieren. GENETIC bleibt aus. Ein echter Import
   und Optimierungslauf erfordern weiterhin die gesonderte Freigabe; Issue #1 erst nach
   dieser späteren Produktionsabnahme schließen.

## Codebelege

- [EOS GET-Rohzeitfenster](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/server/eos.py)
- [EOS Runtime-Arrayauflösung](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/optimization/genetic/configrequest.py)
- [evcc 0.318.1 Messwertfelder](https://github.com/evcc-io/evcc/blob/e967a35e789081adc7bbd1a730c355e8a870c3fb/core/types/types.go)
- [evcc SoC-Retention bei Fehlern](https://github.com/evcc-io/evcc/blob/e967a35e789081adc7bbd1a730c355e8a870c3fb/core/site.go)
- [evcc lesender Gerätestatus](https://github.com/evcc-io/evcc/blob/e967a35e789081adc7bbd1a730c355e8a870c3fb/server/http_config_device_handler.go)
- [evcc Getter-Prüfung](https://github.com/evcc-io/evcc/blob/e967a35e789081adc7bbd1a730c355e8a870c3fb/server/http_config_helper.go)
- [E3/DC ungecachter RSCP-Getter](https://github.com/evcc-io/evcc/blob/e967a35e789081adc7bbd1a730c355e8a870c3fb/meter/e3dc.go)

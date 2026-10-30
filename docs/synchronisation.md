# SoC, Endkundenpreise und Day-Ahead-Ereignis

Diese Erweiterung setzt die drei Ergänzungen in
[Issue #1](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/1) um.
Der Standard bleibt PV-only, Cache-only und `DRY_RUN=true`. Es wurden keine bestehenden
Container verändert und keine produktiven EOS-Schreibzugriffe ausgeführt.

Die [nachträglichen Findings und ihre Korrekturen](FINDINGS_ISSUE_1.md) enthalten den
aktuellen PV-Horizont, evcc-Quellwahl, historische Preis-Rücklesung und erneute
Unraid-Abnahme. Die ursprüngliche HA-Quelle ist nur noch explizit wählbarer Legacy-Modus.

## Einrichtung auf Unraid

1. Zunächst den PV-Dry-run aus der README fertig einrichten. Der Helfer benötigt seine
   eigene beschreibbare `output`-Ablage, dieselbe bleibt nach Containerneustarts erhalten.
   Nur eine Helferinstanz pro EOS verwenden. Dateilocks schützen parallel gestartete
   Instanzen mit derselben Ablage; getrennte Ablagen bieten diese Garantie nicht.
2. In der privaten `config.toml` die gemeinsame `[evcc].url` eintragen. Preise unabhängig
   mit `[prices].enabled=true` aktivieren. SoC benötigt zusätzlich die genaue Gerätekennung,
   den geprüften RSCP-Treiber und einen vorhandenen privaten evcc-Key für geschützte
   lesende GETs. Optionaler HA-Vergleich benötigt privat bereitgestelltes `HA_TOKEN`.
   Compose übernimmt die Umgebungsvariable in den neuen Helfercontainer. Die bestehende
   HA-, evcc- und EOS-Konfiguration wird nicht geändert.
3. In der Compose-Datei des **neuen Helfers** optional ergänzen:

   ```yaml
   command: ["sync", "--config", "/app/config.toml"]
   ```

   `docker compose up -d --build` startet damit nur diesen Helfer. Alle 60 Sekunden
   werden die aktivierten Quellen gelesen, PV separat alle `poll_seconds`.
   `docker compose run --rm eos-pv-helper sync --once` prüft einen einzelnen Zyklus.
4. Für die reine Ereignisprüfung zusätzlich `[trigger].enabled=true` setzen.
   `run_enabled=false`, alle `write_enabled=false` und `DRY_RUN=true` beibehalten.
   `sync-report.json` dokumentiert Quellzeitstempel, Alter, Preisversion, Qualitätsfehler,
   Kontrollhorizont und nutzbaren Tail. Ausstehende morgige Preise melden
   `waiting-publication`; sie sind kein technischer Fehler.
5. EOS muss für Preisimporte bereits `ElecPriceImport` verwenden; die beschriebene Anlage
   wurde inzwischen vom Betreiber so umgestellt. Bei `ElecPriceEnergyCharts` bleibt der
   Import gesperrt. Jede Umstellung erfordert **separate Freigabe** und erfolgt
   außerhalb dieses Helfers. Er nimmt keine automatische Konfigurationsänderung vor.
   Vorher einzelne evcc-Preisintervalle mit LUOX vergleichen; erst dann
   `prices.retail_prices_confirmed=true` setzen.

## Datenverträge und Gebühren

`soc_sample()` akzeptiert ausschließlich `sensor.evcc_battery_soc`, endliche 0..100 %,
Quellalter 0..300 s. Verwendet wird HA `last_reported`, soweit vorhanden, andernfalls
`last_updated`. `last_changed` und die aktuelle Helferzeit ersetzen keine Messzeit.
Bei unverändertem SoC kann `last_changed` alt sein; eine frische HA-Meldung bleibt gültig.
Fehlt auch `last_reported`, wird ein alter `last_updated` vorsichtig als stale abgelehnt.

Der bestätigte Schreibvertrag ist **PUT `/v1/measurement/value` mit Query-Parametern**
`datetime`, `key=e3dc_s10e_pro-soc-factor`, `value=Prozent/100`. Keine `/samples`-Nutzung.
Rohdaten werden über `/v1/measurement/series?key=...&processing=raw&dropna=false` geprüft.
55,5 % bleiben als Faktor 0,555 im Messspeicher erhalten. GENETIC verwendet initiale SoC
in ganzzahligen Prozent: der Simulationsaufruf erhält nach erneuter Frischeprüfung 55 %,
genau wie EOS selbst quantisieren würde. So wird EOS' sonst möglicher stiller Rückfall
auf angenommenen 0-%-SoC verhindert.

Neue Installationen bevorzugen `soc.source="evcc"`. Normale evcc-Zustandswerte enthalten
keinen Frischezeitstempel; der neue RSCP-Statuspfad und dessen Grenzen stehen im
Finding-Bericht. HA wird niemals stillschweigend als Ersatz verwendet. Eine absichtlich
gewählte alte HA-Quelle benötigt jetzt ausdrücklich `source="homeassistant"` und ihre
URL/Token-Felder im `[soc]`-Block; ihre 300-s-Prüfung bleibt unverändert.

`retail_prices()` verlangt explizit EUR, lückenlose Unix-Intervalle von genau 900 Sekunden,
keine Duplikate und endliche Werte. Negative Preise und echte Nullpreise sind gültig.
`prices-source.json` enthält die originalen evcc-Werte in EUR/kWh und den Abrufzeitpunkt;
`prices.json` den EOS-DataFrame mit **`elecprice_marketprice_wh`** in EUR/Wh. Division
durch 1.000 ist die einzige Preisberechnung. Kein Schreiben nach
`elecprice_marketprice_raw_wh`, keine erneute USt, kein erneuter LUOX-Aufschlag, keine
Aktivierung von Bayernwerk Modul 3.

EOS hat tatsächlich Gebühren von 0,1138655 EUR/kWh und 19 % konfiguriert. Beim untersuchten
`ElecPriceImport` wird das fertig importierte Bruttofeld nicht durch `_apply_fees()`
geschickt. Ein echter EOS-Integrationstest prüft dies mit positiven und negativen
Preisen, eingeschalteten Gebühren und einem anschließenden nativen Providerupdate sowie
Simulationslauf. Deshalb müssen diese Gebühren nicht automatisch entfernt werden.
Ein Datei-/JSON-Import könnte die Werte überschreiben und wird abgelehnt. Eine andere
EOS-Version sperrt die Erweiterung bis zur erneuten Vertrags-/Gebührenprüfung.

## Zeitpunkt und Horizont eines Laufs

`day_ahead_version()` prüft den **vollständigen nächsten lokalen Liefertag** in
`Europe/Berlin`. Seine 92, 96 oder 100 Viertelstunden werden gemeinsam mit dem Datum
gehasht. Das Entfernen alter Intervalle aus evcc `forecast.grid` ändert diese Version
nicht. Eine tatsächliche Preisrevision ergibt eine neue Version. Bei Erstinbetriebnahme
gilt eine bereits vorliegende vollständige morgige Veröffentlichung als neue Version.

`coverage()` bildet EOS' begrenzte Intervallmittel nach: keine Lückenfüllung und keine
Verlängerung über die vorhandene Quellkadenz (maximal eine Stunde). Es liest bestehende
rohe PV-, Last- und Einspeisetarifreihen aus EOS. Sämtliche Kontrollslots aller vier
Reihen müssen vollständig sein. Fehlende Tageswerte, Preise oder Last sind Sperren.

Konfiguration aktuell: 24 h Kontrollhorizont, 48 h Prognose, angeforderter Tail 48 h.
EOS begrenzt den Tail auf `min(48, 48 - 24) = 24 h`; ein kürzerer zusammenhängender Tail
ist erlaubt. **24 h sind zwingend, 72 h werden nicht verlangt.** Der Bericht weist
angeforderten, budgetierten und tatsächlich gedeckten Tail getrennt aus. Start ist der
aktuelle EOS-Slot, ab lokaler Mitternacht mit verstrichenen UTC-Sekunden berechnet.
Ein Slotwechsel unmittelbar vor Versand führt zur erneuten Prüfung im nächsten Zyklus.

## Live-Freigaben und Simulationsgrenzen

Erst nach ausdrücklicher Freigabe dürfen `DRY_RUN=false`, `eos.write_enabled=true` und
`--write-eos` gemeinsam gesetzt werden. Im `sync`-Kommando erlaubt dies den bestehenden
PV-Import; SoC und Preise benötigen zusätzlich ihr jeweiliges `write_enabled=true`.
Simulation benötigt separat `trigger.enabled=true` und `trigger.run_enabled=true`.
Jeder SoC-/Preisimport wird roh zurückgelesen, bevor ein Lauf zulässig ist.

Der einzige Simulationsaufruf ist POST `/v1/optimize` mit validiertem Batterie-SoC. EOS
besitzt die Prognosepipeline und GENETIC; der Helfer stellt keinen zweiten periodischen
Optimierungs- oder BrightSky-/Last-Scheduler auf. **Dieser EOS-Endpunkt führt intern
selbst seine normale Prognosepipeline aus**, einschließlich des nativen Cacheverhaltens.
EOS kann dabei bei abgelaufenem eigenem Cache selbst nachladen. Der Helfer ruft weder
`prediction/update` noch externe Wetter-/Börsenpreisendpunkte auf.

`ems.mode=PREDICTION` und `ems.interval=3600` bleiben unverändert. Weil EOS im selben
internen Ablauf Adapter aktualisiert und optional einen Abschluss-Webhook versendet,
sperrt der Helfer bei aktiven Adaptern oder `ems.notify_url`. Ein einzelner GET-Check kann
gleichzeitige administrative Änderungen nicht atomar verhindern; während eines
freigegebenen Laufs daher keine parallele EOS-Umkonfiguration durchführen. Vor Versand
wird die relevante Konfiguration erneut verglichen. Keine Geräte-Steuerbefehle werden
durch den Helfer erzeugt oder ausgeführt.

## Idempotenz und Fehlerbehandlung

`sync-state.json` persistiert die Preisversion **vor** dem POST unter Dateilock mit
`fsync` und atomarem Umbenennen. Erst eine neue, zum Slot passende GENETIC-Antwort mit
vollständigen Entscheidungen und endlichen Kosten wird `succeeded`. Das Ergebnis steht
in `solution-<version>.json`. Diese Datei ist ein Plan, kein Steuerauftrag.

Absturz, Timeout, HTTP-Fehler oder ungültige Antwort nach dem Claim bleiben `uncertain`.
Neustarts versenden dann keinen zweiten POST. EOS bietet hier keinen serverseitigen
Idempotenzschlüssel: garantiert wird höchstens ein Versand je Version und gemeinsamer
Statusablage, nicht ein nach Absturz beweisbar exakt einmal abgeschlossener Lauf.
Vor einer manuellen Wiederfreigabe den tatsächlichen EOS-Lauf und sein Ergebnis prüfen;
Statusdatei nicht pauschal löschen. Dry-run speichert keine Live-Claims und verhindert
einen später ausdrücklich genehmigten Lauf nicht.

Veralteter SoC, PV-Lücken, fehlende Preisabdeckung und gesperrte Provider werden in
`sync-report.json`, Logs und Healthcheck sichtbar. Ein vor Versand ungültiger Input
verbraucht die Preisversion nicht; eine spätere gültige Eingabe darf sie neu prüfen.

Bei dynamischem PV-Ende wird der echte Mitternachts-Preispräfix als begrenzter nativer
Runtime-Array übergeben. So kann die EOS-Auflösung keine gespeicherten älteren
PV-Tailpunkte wieder anhängen. Fehlender Preispräfix wird ausdrücklich gemeldet, nicht
mit erfundenen historischen Werten gepolstert.

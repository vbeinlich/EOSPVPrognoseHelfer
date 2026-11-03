# PR #24 – technischer Gegenreview und PASS/BLOCKED-Abnahme

Prüftag: 03.11.2026. Geprüfter PR-Head:
`6af922e4e38bb12d49acbaf02bee0b1fd2da27db`.
Review-Checkout: `review/pr24-audit`, getrennt von `dashboard/ems-v1`.
PR: https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/24

**Gesamturteil: BLOCKED für die vollständige fachliche Dashboard-v1.0-Abnahme
und den unbeaufsichtigten Unraid-Dauerbetrieb.** Ein begrenzter einmaliger privater
Leseexport ist technisch möglich, sofern die unten genannten Vorbedingungen
bestätigt werden. Dieser Review führt ihn auf Unraid nicht aus.

Methodik: erneute technische Gegenprüfung mit eigenen Originaldaten-Proben und
Browsergegenbeispielen, unabhängig von den bisherigen synthetischen Assertions.
Derselbe Assistent hat die Implementierung erstellt; dieser Bericht ist daher
keine personell unabhängige Zweitfreigabe. Eine solche bleibt gesondert nötig.

## Abnahmematrix

| Prüffrage | Ergebnis | Nachweis / Grenze |
| --- | --- | --- |
| 1. Grafiken mit echten gespeicherten GENETIC-Antworten | **PASS teilweise / BLOCKED vollständig** | Je 24 Originalstunden vom 29./31.10.: SoC-Werte, Preis-, PV- und Lastkurven stimmen numerisch; 0 Browserfehler/0 externe Requests. SoC-Zeitpunkt ist falsch, Energieflächen fehlen zu Recht. Vollständige NAS-/Claimzuordnung nicht bewiesen. |
| 2. Tatsächlich vorhandene Batterieenergien im bisherigen Ergebnis | **PASS für die Inventur** | Keine Batterie-Lade-/Entladeenergiearrays und kein Herkunftssplit in den zwei Originalantworten. SoC, Netzbezug, Einspeisung, Kosten/Erlöse, Verluste und Freigaben vorhanden. |
| 3. Vollständige grüne/blaue/orange Anzeige und Vollzyklen | **BLOCKED** | Fehlende Flussdaten, keine produktive Quelle für den neuen optionalen Flussvertrag, kein Replay-Sidecar-Adapter; zusätzlich Darstellungsfehler R24-02 bis R24-04. |
| 4. Gesonderter fester nativer Offline-Replay | **PASS für 29./31.10., begrenzte Modell-Aussage** | Originalparameter und gespeicherte Freigaben reproduzieren Vergleichsreihen, Summen und Endwerte. Lesende Herkunftserfassung ändert kein Ergebnis. Kein Beweis historischer Ausführung oder atomarer damaliger Laufoptionen. 30.10. bleibt ungeprüft. |
| 5. Vorhandenes Produktionsimage | **PASS für die isolierte lokale Imagekopie** | Unverändertes dokumentiertes Image, UID 10001, network none, read-only, kein Projektcode-Mount, statischer Bundle-Leser und Fehlererhalt bestanden. Aktueller Live-Digest/Dateirechte auf Unraid nicht erneut gelesen. |
| 6. Einmaliger privater HTML-Export ohne Konfigurationsänderung | **PASS als begrenzter technischer Vorschlag** | Wrapper benutzt kurze `docker exec`-Leseroutine; kein zusätzlicher Helfer, kein EOS-POST, kein Scheduler/Port. Gemeinsames SH-Lock kann einen später startenden Writer verzögern. Eine Garantie völlig unbeeinflussten Timings wird nicht gegeben. |

## Konkrete Befunde

### R24-01 · P1 · Vollständige Energieanzeige mit bisherigen Realdateien noch nicht angeschlossen

[`dashboard.py`, Flussvertrag und `enrich`](../src/eos_pv_helper/dashboard.py#L34)
liest ausschließlich vier neue Felder aus `solution.result` sowie passende
`battery_flow_*`-Zeit-/Rastermetadaten. Die echten vorhandenen Antworten vom
29./31.10. enthalten keines dieser vier Felder. Deshalb liefern alle 48 geprüften
Originalintervalle `proof=unavailable`: grüne/blaue/orange Mengen und Vollzyklen
stehen auf `Nicht belegt`. Das ist die korrekte Datenlückenanzeige, aber keine
vollständige Darstellung der gewünschten Batterieflüsse.

Der vorhandene Economics-Replay exportiert bereits Gesamt-Lade- und
Entladeenergien als zusätzliche `slots`. Der Dashboard-Cachepfad übernimmt daraus
nur den monetären Modellvergleich; `enrich` liest Batterieflüsse weiter aus der
Originallösung. Ein erfolgreicher Economics-Report allein füllt die fehlenden
Balken deshalb nicht. Ein Quelle-spezifischer Replay-Sidecar wird in PR #24
überhaupt nicht eingelesen.

**Erforderlich:** eigener geprüfter, unveränderlicher Replay-Sidecar mit
Originalbytehash, Projektionshash, Engine-/Tabellen-/Dependency-Nachweis,
Originalzeitachse, Gleichheitsprüfung und expliziter Energiebasis. Dashboardadapter
für diesen Sidecar; Kennzeichnung `nachträglich berechneter Modell-Replay`.
Original-JSON, ursprüngliche Claims und damalige Archivbelege unverändert lassen.
Kein neuer Writer im regulären Dry-Run und kein heimlicher Replay bei HTML-Refresh.

### R24-02 · P2 · Stundenanfangs-SoC um eine halbe Originalperiode verschoben

[`dashboard_view.py:46`](../src/eos_pv_helper/dashboard_view.py#L46) zeichnet
`battery_soc_per_hour` bei `x + w/2`. Die native Simulation dokumentiert und liefert
SoC **am Anfang** des Intervalls, nicht in dessen Mitte. Die Browsergegenprobe
bestätigt für beide Originalantworten alle 24 korrekten SoC-Werte, aber falsche
Zeitpositionen: im vorhandenen Stundenraster **+30 Minuten**, bei 15 Minuten
entsprechend +7,5 Minuten.

**Erforderlich:** SoC an der nachgewiesenen Originalzeit des Zustands verorten;
letzten End-SoC nur separat darstellen, falls tatsächlich belegt. Keine still
interpolierten Zustände bei gekürzten historischen Teilintervallen erfinden.

### R24-03 · P2 · Gestapelte PV-/Netzladung kann oben abgeschnitten werden

[`dashboard_view.py:37–44`](../src/eos_pv_helper/dashboard_view.py#L37) normiert
auf das Maximum einzelner Herkunftskomponenten. Gestapelt wird deren Summe.
Eigenständiges synthetisches Gegenbeispiel: 1000 Wh PV + 1000 Wh Netz im selben
Intervall. Die obere Balkenkante liegt bei **SVG-y = -45**, außerhalb der bei
0 beginnenden ViewBox. Der kombinierte Ladebalken wird abgeschnitten.

Das bisherige Fixture deckt überwiegend getrennte Herkunftsfenster ab.
**Erforderlich:** positive Achse auf gesamte gestapelte Ladung auslegen und
kombinierte PV-/Netzladung als Browserregression prüfen. Positive/negative
Energieskalen und SoC-Achse weiterhin konsistent halten.

### R24-04 · P2 · Leere Historie zeigt fälschlich null Lade-/Entladefenster

[`dashboard_view.py:59–64`](../src/eos_pv_helper/dashboard_view.py#L59) lässt
`windows([])` als 0 erscheinen. Ohne verfügbare historische Claims enthält die
7-Tage-Ansicht null Zeilen, zeigt aber **0 / 0** Lade-/Entladefenster. Reproduziert
mit den echten, ausdrücklich nicht zugeordneten Originalantworten.

**Erforderlich:** leere/ungeklärte Abdeckung als `Nicht belegt` oder `—` markieren.
Null Fenster setzt eine vollständig bekannte Datenbasis voraus.

## Was die bisherigen Ergebnisse tatsächlich enthalten

Inventar beider privaten gespeicherten GET-Originalantworten:

| Daten | Vorhanden? | Aussage |
| --- | --- | --- |
| `ac_charge`, `dc_charge`, `discharge_allowed` | ja | Freigaben/Faktoren; keine Lade-/Entladeenergie |
| `result.battery_soc_per_hour` | ja, 24 Werte | modellierter Zustand am Intervallanfang |
| `grid_consumption_wh_per_hour`, `grid_feed_in_wh_per_hour` | ja | gesamter Netzbezug/-export; kein Batterie-Herkunftsnachweis |
| `load_wh_per_hour`, Kosten/Erlöse, Verluste und Gesamtsummen | ja | native Modell-Ergebniswerte, keine zusätzliche Brutto-Batteriebilanz |
| Preis und Vergütung im Ergebnis | ja | gespeicherte Ergebnispreise |
| Originale PV-/Last-/Preisreihen und Batterie-/Inverterparameter | in `parameters` vorhanden | gespeicherte Solver-Eingaben; historische unabhängige Requestbindung separat beurteilen |
| Batterie-DC-Lade-/Entladeenergie als Originalzeitreihe | **nein** | weder Gesamtladung/-entladung noch Herkunftsarrays vorhanden |
| Exakter PV-/Netzladeanteil, Lade-/Entladefenster, Vollzyklen | **nicht gespeichert** | aus Freigaben oder Netzbezug nicht ableitbar |

Die vier in PR #24 erwarteten Flussarrays sind:
`battery_charge_dc_wh_per_hour`, `battery_discharge_dc_wh_per_hour`,
`battery_pv_charge_dc_wh_per_hour`, `battery_grid_charge_dc_wh_per_hour`.
Auch die erforderliche `battery_flow_energy_basis`-/Start-/Rasterbindung fehlt.
Diese Originale werden nicht nachträglich erweitert.

Für den 30.10. ist weiterhin kein lesbarer Originalinhalt samt ursprünglichem
Sync-State verfügbar. Eine Dateiliste oder die echten Nachbartage beweisen
keinen Inhalt des fehlenden Tages. Es wurde keine Datei rekonstruiert und kein
`succeeded`-Claim erfunden. Die echten Browserproben zeigen deshalb korrekt
`Kein Plan` in der Erfolgsübersicht, während beide unzugeordneten Originale im
Archiv auswählbar bleiben. Eine vollständige Unraid-End-to-End-Abnahme ist das nicht.

## Offline-Replay: nachgewiesen möglich, Herkunft und Energiescope ausdrücklich festlegen

Geprüfte native EOS-Revision:
`8a8cd43a1915668927eda5504b7de039c2e762b4`.
Der bestehende Adapter prüft die Fingerprints von Batterie, Wechselrichter,
Simulation, Parametern, Interpolator und probabilistischer Überlappungstabelle.

Die neue Reviewprobe führt ausschließlich feste Vorwärtswiedergaben der
**gespeicherten** Freigaben mit `baseline=False`, `load_scale=1` aus.
`GeneticOptimization.optimize_ems`, HTTP sowie Socket-Verbindungen sind gesperrt;
die lokale Testumgebung hat zusätzlich `network none` und keine Geräte-/Live-Mounts.
Keine Suche nach Kandidaten, keine neue Konfiguration, kein Baseline-Lauf.

Ergebnisse für 29./31.10.:

- Alle acht bestehenden Vergleichsreihen, vier Gesamtsummen, Endenergie und
  gemeinsame Endwertbewertung erfüllen die vorhandenen Prüftoleranzen
  `rel_tol=1e-9`, `abs_tol=1e-5`.
- Größte absolute Abweichung der gemeinsamen Reihen: ungefähr
  `2,27e-13` bzw. `1,14e-13`. Das ist numerische Übereinstimmung, keine behauptete
  Bitidentität sämtlicher ursprünglicher Laufumstände.
- Zusätzlich unmittelbar erfasste native Last-, EV-SoC- und Hausgeräte-Reihen
  stimmen mit der jeweiligen Originalantwort überein, einschließlich fehlender
  EV-/Gerätedaten.
- Zwei rein beobachtende Wrapper um `Inverter.process_energy` und
  `Inverter.charge_battery_from_grid` erfassen Änderungen der nativen Ladezähler.
  Der erste Pfad lädt aus dem vom nativen Modell bestimmten PV-Überschuss, der
  zweite ausdrücklich aus dem Netz. Die beobachtete Summe entspricht exakt der
  nativen Gesamtladung. Instrumentierte und uninstrumentierte Adapterergebnisse
  sind vollständig gleich; kein Ersatzmodell.
- Die Batterie-Energiebilanz je Intervall stimmt mit dem SoC-Verlauf überein,
  einschließlich Wirkungsgraden. Am 29.10. treten positive Brutto-Ladung und
  Brutto-Entladung innerhalb derselben Stunde auf. SoC-Differenzen verlieren
  deshalb Flussinformationen; eine Differenzenmethode ist kein Ersatz.

### DC-Anschluss und interner Speicher sind verschiedene Bezugsgrößen

Die geprüfte native Batterie definiert:

- `_charged_raw_wh_per_slot`: DC-Eingang **vor** internem Ladewirkungsgrad.
- gespeicherter Energiezuwachs: DC-Eingang × `charging_efficiency`.
- `discharged_energy_wh`: gelieferter DC-Ausgang **nach** internem Entladeverlust.
- interne Speicherentnahme: DC-Ausgang / `discharging_efficiency`.

Der vorhandene Economics-Adapter speichert unter `battery_charge_dc_wh` den
DC-Eingang und unter `battery_discharge_dc_wh` den gelieferten DC-Ausgang.
Diese beiden Felder dürfen nicht einfach als interne Speicheränderungen umetikettiert
werden. Für interne äquivalente Vollzyklen gilt bei konstanter Effizienz:

```
EFC = Summe(interne Speicherentnahme) / nutzbare interne Kapazität
interne Speicherentnahme = gelieferte DC-Entladeenergie / Entladewirkungsgrad
```

Bei einer bewusst anders definierten Ausgangsenergie-Kennzahl muss deren Scope
und gegebenenfalls effizienzbereinigter Nenner gesondert angegeben werden. In den
Originalen unterscheiden sich die beiden EFC-Definitionen messbar.

**Grenze:** Replaywerte sind heute nachgerechnete Modellgrößen aus gespeicherten
Eingaben. Sie sind keine damaligen Messungen, keine tatsächlich ausgeführten
Geräteflüsse und kein nachträglicher historischer Request-/Optionsbeweis.
`exact_solver_options_proven=false` und Issue #21 bleiben unverändert.
Hashbindung belegt Konsistenz, nicht automatisch Authentizität fremder Dateien.
Fehlende Originaleingaben oder fehlgeschlagener Replay müssen zur Ablehnung des
Sidecars führen. Insbesondere für den 30.10. besteht keine Replayfreigabe auf Basis
erfundener oder aus heutigen Dateien übernommener Daten.

## Sicherheit und tatsächliche Reichweite des Image-Tests

Geprüft wurde die unveränderte **lokale Kopie des zuletzt dokumentierten**
Produktionsimages:
`ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`.

Neu durchgeführter Bundle-Test: UID 10001, read-only Root-Dateisystem und
Input-Mount, network none, alle Capabilities entfernt, no-new-privileges,
kein Projektcode-Mount. Leser und letzter-gültiger-Stand bei beschädigtem
Sync-State: **PASS**; Quellbytes und Änderungszeiten unverändert.

Das ist keine erneute Live-Inventur auf Unraid. Der produktive `docker exec`
erbt dessen vorhandene Mounts und Netzwerkrechte; die strengere Isolation des
lokalen Tests wird durch `exec` nicht nachträglich erzwungen. Sicherheit folgt
hier aus geprüftem und per SHA-256 fixiertem Code, nicht aus einer neuen Sandbox
innerhalb des laufenden Helfers. Der Leser ruft weder native Simulation noch API
auf und öffnet keine Konfiguration/aktuellen Live-Prognosen als historische Quelle.

Beachten: [`dashboard.py:263`](../src/eos_pv_helper/dashboard.py#L263) hält ein
SH-Lock; [`sync.py:126`](../src/eos_pv_helper/sync.py#L126) nimmt ein blockierendes
EX-Lock, auch im unveränderten Produktionsimage. Der Leser wartet nicht auf einen
schreibenden Sync, kann aber einen nachfolgenden Sync bis zum Ende seiner Lesephase
verzögern. Eine Aussage „ohne jede Beeinflussung des normalen Timings“ wäre falsch.
Der Wrapper begrenzt den Leser auf 45 Sekunden; reale Datenmenge/Laufzeit muss
vor minütlichem Dauerbetrieb geprüft werden.

## Empfehlung: erster einmaliger privater Unraid-Sichttest

**Empfohlen:** einmaliger Leseexport ohne Economics-Cache und ohne Replay im
Produktionscontainer. Nicht als vollständige farbige Funktionsabnahme ausgeben.
Bisher bekannte Darstellungsfehler ausdrücklich beachten; für zeitliche Beurteilung
zunächst Originaltabelle statt verschobener SoC-Punkte verwenden.

1. Nur lesend bestätigen, welcher einzelne Helfer läuft und ob dessen tatsächlicher
   Image-Digest dem oben geprüften Stand entspricht. Abweichung: hier abbrechen,
   keine Images ziehen/wechseln, keinen Container neu starten.
2. Nach einem ohnehin regulär abgeschlossenen Dry-Run, abseits des nächsten
   erwarteten Triggers, Lesbarkeit von vorhandenem `sync.lock`, `sync-state.json`,
   `sync-report.json` und Lösungen prüfen. Fehlende Rechte oder beschädigte Dateien:
   abbrechen; kein `chmod`, kein Reparieren/Neuhashen und kein zusätzlicher Lauf.
3. Das geprüfte Codebundle und den Wrapper in einen getrennten privaten
   Review-Werkzeugordner kopieren. Nur den **eigenen neuen** privaten Zielordner
   anlegen; keine produktiven Mounts oder Freigaben ändern. Ziel darf weder
   Helfer-Ausgabe noch deren Vor-/Unterordner sein. Bestehenden privaten
   Dateiübertragungsweg verwenden, keinen neuen öffentlichen Share/Port.
4. Beide Codes mit den festen geprüften Hashes vergleichen:

   ```text
   ems-dashboard-reviewed.pyz
   b8fe60da4d3207a08a3509c979d21dc46552e1e6d90dd3fa2f120d3af4655c3a

   unraid-ems-dashboard.sh
   bb1f10626f2b9b623011987ae88722530ef4b2243f52ddb5f4b010472bc4efaa
   ```

5. Genau einmal folgenden Leseexport starten, Pfade an den eigenen privaten
   Reviewordner anpassen:

   ```bash
   /bin/bash /mnt/user/appdata/ems-dashboard-review/tools/unraid-ems-dashboard.sh \
     /mnt/user/appdata/ems-dashboard-review/tools/ems-dashboard-reviewed.pyz \
     b8fe60da4d3207a08a3509c979d21dc46552e1e6d90dd3fa2f120d3af4655c3a \
     /mnt/user/appdata/ems-dashboard-review/private
   ```

   Kein Scheduler, kein dauerhaftes Helferprogramm, keine zweite Instanz,
   keine neue Optimierung, kein EOS-/Geräteaufruf. Der kurze Leser im bestehenden
   Container beendet sich nach dem Export; ausschließlich eigene Review-Dateien
   werden geschrieben. Nicht parallel zur laufenden schreibenden Syncphase testen.

6. Nur die fertige private `index.html` über den vorhandenen privaten Dateizugang
   zum eigenen Browser übertragen/öffnen. Plan-ID, Start 13 Uhr, 24 Originalstunden,
   SoC-Werte und Forecastwerte stichprobenartig gegen die JSON-Originale prüfen.
   Fehlende Batterieflüsse müssen sichtbar `Nicht belegt` bleiben. Ohne echten
   Claim keine Erfolgsmeldung erzwingen. Nach drei Minuten kann der einmalige
   Export erwartungsgemäß als veraltet erscheinen: Es wurde kein Scheduler aktiviert.
7. Exit 2 oder Fehleransicht: privat protokollieren und stoppen. Kein GENETIC-Lauf
   zum „Reparieren“. Erst nach Beseitigung der Befunde, realer Claim-/Datenabnahme
   und gesonderter Betreiberfreigabe einen automatischen Betrieb erwägen.

Falls eine vorhandene private, konsistente Diagnosekopie verfügbar ist, ist die
Anzeige aus dieser Kopie auf dem Review-Rechner der erste Schritt ohne zusätzlichen
Prozess im produktiven Container. Für den ersten Live-Leseexport sind ein vorhandener
sicherer Dateizugang und echte Metadaten erforderlich; diese wurden hier nicht ersetzt.

## Prüfartefakte und Reproduzierbarkeit

Neue Proben dieses Reviews:

- [`review/pr24_native_audit.py`](../review/pr24_native_audit.py): Inventur,
  fester nativer Original-Replay, lesende Herkunftszähler und Energiebilanz.
- [`review/pr24_real_ui.mjs`](../review/pr24_real_ui.mjs): echter Browser gegen
  unveränderte Originalwerte; SoC-Zeitabweichung, leere Historie und gestapeltes
  synthetisches Gegenbeispiel werden als Befunde aufgezeichnet.
- [`review/pr24_findings.json`](../review/pr24_findings.json): öffentliche
  Ergebniszusammenfassung ohne private Energie-/Kostenwerte oder Originalhashes.

Die Originale, ihre bytegenauen Hashes, Replay-Energiereihen und privaten HTML-
Ansichten bleiben ausschließlich im ignorierten `private/`-Verzeichnis. Keine
Originaldaten werden veröffentlicht. Bereits grüne PR-CI ist ein früherer
Regressionsnachweis; deren 632 Tests wurden nicht als Ersatz für diese gezielten
fachlichen Gegenproben behandelt oder hier als neu ausgeführt behauptet.

Innerhalb der isolierten lokalen Testumgebung mit gepinntem EOS-Quellbaum,
`PYTHONPATH=src:scripts:/opt/eos/src`, read-only Original-Mounts und einem eigenen
schreibbaren `/audit`-Ziel ist die neue Probe so reproduzierbar:

```bash
python review/pr24_native_audit.py \
  --original /original29.json --original /original31.json --native \
  --output /audit/private-result.json --html /audit/original-dashboard.html \
  --counterexample-html /audit/stacked-example.html
```

Die erzeugten privaten Dateien dann auf dem lokalen Browser-Prüfrechner verwenden:

```bash
node review/pr24_real_ui.mjs --browser /PATH/TO/CHROMIUM \
  --html /PRIVATE/original-dashboard.html --expected /PRIVATE/private-result.json \
  --stacked-html /PRIVATE/stacked-example.html --output /PRIVATE/browser-findings.json
```

Die Browserprobe protokolliert erwartete Gegenbefunde, statt bekannte Fehler als
erfolgreiche Produktabnahme zu verschweigen. Die JSON-Ausgabe entscheidet über
PASS/BLOCKED; ein erfolgreicher Prozessabschluss bedeutet nur, dass die Prüfung
vollständig ausgeführt wurde. Keine dieser Proben auf dem Produktionshost starten.

**Unverändert:** PR #24 und dessen Runtimecode; keine Merges, Releases,
Optimierersuchen, Geräteaktionen, neuen produktiven Container oder Änderungen
an produktiven Dateien, Konfigurationen, Schedulern und Ports.

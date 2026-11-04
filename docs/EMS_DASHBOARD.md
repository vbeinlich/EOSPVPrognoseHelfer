# EMS Dashboard v1.0 – privater Unraid-Betrieb

Aktueller Korrekturstand: [versionierter Offline-Replay und private Befehle](REPLAY_SIDECAR.md),
[PASS/BLOCKED-Abschlussbericht](DASHBOARD_FINAL_REVIEW.md). Die nachstehenden
Grundlagen bleiben gültig; interne Replay-Energie und Vollzyklen folgen dem neuen Vertrag.

Status: **Reviewvorlage, keine Deploymentfreigabe.** Basis ist PR #23,
`38d7ea31182cbcc5ed07e7b496bdcbbecad952fb`. Erst die notwendigen Reviews
abschließen; die folgenden Installationsschritte wurden auf Unraid nicht ausgeführt.

Das Dashboard ist eine vollständige lokale HTML-Datei. Der kurze Exportjob liest
vorhandene Ergebnisse. Er startet weder Helferschleife noch Optimierer und enthält
keinen Webserver, Port, Geräteclient oder Steuerungsendpunkt. Inspector, Economics-
Vertrag und der von Doctor verwendete historische Validator werden wiederverwendet.

## Bedienung

- Oben: letzter zugeordneter erfolgreicher GENETIC-Plan, ursprüngliche Modellkosten,
  simulierter Netzbezug im Kontrollhorizont und gegebenenfalls gespeicherter Modellvergleich.
- Planarchiv: einzelne Pläne auswählen; der aktuelle `waiting-publication`-Status
  blendet erfolgreiche ältere Pläne nicht aus. Die oberen Karten bleiben ausdrücklich
  beim letzten erfolgreichen Plan; Diagramme und Intervalle folgen der Auswahl.
- 24 Stunden: Originalintervalle des gewählten Plans. 7/30 Tage: gemeinsame UTC-
  Zeitachse bis zum Ende des jüngsten 24-h-Plans. Anzeige immer Europe/Berlin.
- Grün = gespeicherte PV-Ladung, Blau = gespeicherte Netzladung, Orange = gespeicherte
  Entladung, Violett = gespeicherter Batterie-SoC. Graue Ladebalken bedeuten Energie
  mit unbekannter Herkunft. Kleine graue Markierungen bedeuten fehlende Flussdaten.
- Zeile mit Maus oder Enter/Leertaste, alternativ Balken auswählen: Originalindex,
  Freigaben, unveränderte Modellwerte, gespeicherte Prognosen, Hashes und Nachweisstatus.
  Lange Zeiträume besitzen eine Intervall-Paginierung mit 100 Zeilen.
- Nachweis fehlt: `Nicht belegt`, niemals eine erfundene Null. Unbekannte Teile von
  Summen/Fenstern bleiben ausdrücklich markiert. Die Auswahl bleibt bei Neuanzeige
  erhalten, soweit der Browser Session Storage für lokale Dateien erlaubt.

## Was die Zahlen nachweisen

`ac_charge`, `dc_charge`, `discharge_allowed` sind Faktoren/Freigaben. Aus ihnen,
Preis, PV-Angebot oder SoC-Differenzen werden keine Batterieflüsse abgeleitet.
Netzbezug ist nicht automatisch Batterie-Netzladung. Modellkosten sind keine
Ersparnis, und ein Dry-Run ist kein Ausführungsnachweis.

Vorhandene EOS-Antworten enthalten nicht zwingend Lade-/Entladeenergien und keine
belegte Herkunft. Diese alten Dateien bleiben unverändert; das Dashboard zeigt
ihre Freigaben, SoC, vorhandenen Modellwerte und gespeicherten Solverprognosen.
Es werden keine fehlenden historischen Quellen durch heutige `prices.json`,
`forecast.json` oder `soc.json` ersetzt.

Für gespeicherte Batterieflüsse versteht der Leser folgenden expliziten Vertrag
in `solution.result` (kein Writer und kein Backfill in diesem PR):

```json
{
  "battery_flow_energy_basis": "battery_dc",
  "battery_flow_interval_seconds": 900,
  "battery_flow_start_utc": "2026-10-30T12:00:00+00:00",
  "battery_charge_dc_wh_per_hour": [100, 200],
  "battery_discharge_dc_wh_per_hour": [0, 0],
  "battery_pv_charge_dc_wh_per_hour": [80, 0],
  "battery_grid_charge_dc_wh_per_hour": [0, 200]
}
```

Alle Arrays enthalten **Wh pro tatsächlichem Originalintervall**, trotz des
historischen `_per_hour`-Namens; niemals eine Viertelstundenenergie vervierfachen.
Zeitbasis/Raster müssen exakt zum Plan passen. Alle Werte müssen endlich und
nicht negativ sein. Beide Gesamtarrays müssen vollständig sein; Herkunftsarrays
entweder beide vollständig oder beide fehlen. PV+Netz darf die Gesamtladung nicht
überschreiten; der Rest ist unbekannte Herkunft. Die Zahlen sind gespeicherte
Simulationsergebnisse, keine Messung und keine unabhängige Authentizitätsgarantie.
Bisherige EOS-Dateien werden nicht als Produzenten dieses neuen optionalen Vertrags
behauptet. Synthetische Fixtures demonstrieren dessen positive und negative Fälle.

Lade-/Entladefenster zählen zusammenhängende Intervalle mit positiver gespeicherter
Energie; Freigaben erzeugen keine solchen Fenster. Äquivalente Vollzyklen verwenden im korrigierten Stand ausschließlich
interne Speicherentnahme geteilt durch nutzbare interne Kapazität
`capacity_wh * (max_soc_percentage - min_soc_percentage) / 100`.
Fehlende Kapazität/interne Entnahme ergibt keinen Vollzykluswert; vorhandene DC-Ausgangsenergie allein genügt nicht.

Bei überlappenden Plänen gewinnt pro Zeitpunkt der neueste schon verfügbare
`status=succeeded`-Plan, frühestens ab `max(start_utc, claimed_at_utc)`.
Nur Kontrollintervalle zählen, kein Tail. Aufgeteilte Intervalle werden zeitanteilig
gewichtet, ausdrücklich als Annahme innerhalb des ursprünglichen Intervalls;
Originalwerte bleiben im Detail erhalten. Lücken werden nicht mit Null gefüllt.
Kosten-/Savings-Gesamtergebnisse verschiedener überlappender Horizonte werden nie
zu einer 7-/30-Tage-Ersparnis addiert.

Die aktive Lesemenge umfasst 37 Tage vor dem jüngsten erfolgreichen Planstart,
damit auch vorlaufende Kontrollhorizonte den sichtbaren 30-Tage-Zeitraum abdecken.
Ältere beanspruchte Originale bleiben auf Unraid erhalten. Sicherheitsgrenzen:
4096 aktive Pläne, 8 MB je Lösung, 256 MB Lösungsbytes, begrenzte Archivgrößen aus
dem unveränderten Inspector. Bei Grenzüberschreitung Fehlermeldung und letzter
gültiger Stand; keine automatische Löschung. Sehr hohe Ereignisfrequenzen mit
großen Horizonten sind vor privater Aktivierung gesondert auf Laufzeit/Reportgröße
zu prüfen. Fehlende oder beschädigte alte, nicht mehr aktive Archive werden nicht
nachträglich repariert.

R1/R2/R3 bleiben bestehen: vorhandene Metadaten werden vom gemeinsamen historischen
Prüfvertrag validiert. Legacy bleibt `legacy_limited` bzw. `unproven`, ohne neue
Bestätigung. `exact_solver_options_proven=false`, Issue #21 bleibt offen.

## Werkzeuge auf dem Review-Rechner vorbereiten

Auf einem Linux-Rechner mit Python 3.11+ und IANA-Zeitzonendaten, aus dem geprüften
Dashboard-Checkout:

```bash
python3 scripts/build_ems_dashboard.py --output /PRIVATE/ems-dashboard.pyz
sha256sum /PRIVATE/ems-dashboard.pyz scripts/unraid-ems-dashboard.sh
```

Der Build liest ausschließlich freigegebene Code-Dateien und erzeugt ein
deterministisches stdlib-Zipapp. Keine private Lösung, Config oder Zugangsdaten
werden eingebettet. Für dieselbe Revision muss der Bundlehash identisch sein.
Hash und exakten Git-Commit in der privaten Abnahme festhalten. Nach Codeänderung
neu bauen und prüfen; niemals alten Hash und neuen Code mischen.

Benötigt auf Unraid: Bash, Docker-CLI, `flock`, `timeout`, `readlink`, `stat`,
`sha256sum`, `sync`, `mktemp`, `cmp`, `sed`, `head`, `mv`. Python 3.11+ und
Zeitzonendaten werden im **bereits laufenden** Helfer verwendet. Der Wrapper prüft
lokalen Docker-Socket, genau einen passenden laufenden Helfer und dessen vorhandenes
`/output`-Mount. Bei mehreren Helfern nichts stoppen oder starten: Zuordnung erst
privat klären. Kein Docker-Socket wird in einen neuen Container gemountet.

## Private Installation – erst nach Reviewfreigabe

1. Einen privaten Werkzeugordner und einen **getrennten** privaten Anzeigeordner
   anlegen. Beispielwerte im Folgenden anpassen:

   ```bash
   umask 077
   mkdir -p /mnt/user/appdata/ems-dashboard/tools
   mkdir -p /mnt/user/private-ems-dashboard
   chmod 700 /mnt/user/appdata/ems-dashboard/tools
   ```

   Der Anzeigeordner darf weder das Helfer-`/output` noch dessen Unter- oder
   Oberordner sein. Der Wrapper prüft die aufgelösten Hostpfade vor seinem ersten
   Schreibzugriff. Keine Originaldatei in den Anzeigeordner verschieben.

2. Nur das geprüfte `ems-dashboard.pyz` und `scripts/unraid-ems-dashboard.sh` über
   den bestehenden privaten Übertragungsweg in den Werkzeugordner kopieren.
   Die lokal geprüften SHA-256-Werte nach dem Transfer auf Unraid vergleichen.
   Keine Rohpläne nach GitHub oder in einen öffentlichen Share laden.

3. Den Anzeigeordner über einen bereits zugriffsgeschützten privaten Dateizugang
   lesbar machen. Beispielsweise in der Unraid-Oberfläche einen SMB-Share
   `private-ems-dashboard` auf **Private** stellen, Gastzugriff deaktivieren und
   nur dem Betreiber Leserechte geben. Vorhandenen geschützten Dateizugang
   bevorzugen. Kein Webserver und keine neue Portfreigabe.

4. Einmaliger manueller Leseexport (ersetze `GEPRUEFTER_BUNDLE_SHA256` durch den
   **festen** zuvor überprüften Wert; nicht zur Laufzeit aus unbekanntem Code ableiten):

   ```bash
   /bin/bash /mnt/user/appdata/ems-dashboard/tools/unraid-ems-dashboard.sh \
     /mnt/user/appdata/ems-dashboard/tools/ems-dashboard.pyz \
     GEPRUEFTER_BUNDLE_SHA256 \
     /mnt/user/private-ems-dashboard
   ```

   Dieser Befehl entdeckt den bestehenden Helfer, führt ausschließlich den
   gebündelten Python-Leser mit `-I -S -B` darin aus und beendet ihn wieder.
   Die normale Helferschleife, produktive Mounts, Parameter und Freigaben ändern
   sich nicht. Keine neue `docker run`-/GENETIC-Instanz.

5. Im privaten Browser `\\UNRAID\private-ems-dashboard\index.html` öffnen
   (entsprechende lokale `file://`-Adresse). Die Datei vollständig laden, JavaScript
   zulassen, Status/Zeiten/Originalwerte prüfen. Der Browser lädt die Datei alle
   60 Sekunden neu, ohne HTTP-Abfrage. Dateiänderungen über den privaten Share
   werden beim nächsten Neuladen sichtbar; keine unveränderliche Downloadkopie
   im lokalen Downloadordner öffnen. Die tatsächliche SMB-/Browserkombination
   gehört zur privaten Unraid-Abnahme.

6. Erst nach erfolgreicher manueller Prüfung den **gleichen Leseexport** mit einem
   bereits vorhandenen Unraid-Scheduler, etwa User Scripts, minütlich planen.
   Ein mögliches Script besteht nur aus dem Befehl aus Schritt 4 mit absolutem
   Pfad und festem geprüften Hash. Kein Aufruf von `eos-pv-helper`, Sync,
   `/optimize`, `--write-eos` oder anderen Produktionsaktionen. Dieses Repository
   installiert weder Scheduler noch Plugin automatisch.

Jeder reguläre Dry-Run wird nach Abschluss in den bestehenden Dateien sichtbar.
Der Lesejob prüft diese im Minutentakt: Veröffentlichung normalerweise innerhalb
60 Sekunden, Browseranzeige innerhalb weiterer 60 Sekunden. Es ist kein Hook in
den Scheduler und kein zusätzlicher Optimierungslauf nötig. Das gemeinsame
bestehende `sync.lock` schützt die Leseaufnahme; bei schreibendem Sync sofortiger
Fehlversuch statt Eingriff in den laufenden Job. Ein eigenes Exportlock verhindert
überlappende Leser. Der Leser ist auf 45 Sekunden begrenzt.

Der Lesejob schreibt nur die eigene HTML-Datei und Exportlock/temporäre Dateien
im privaten Ziel. Komplettes HTML wird im selben Verzeichnis geschrieben,
synchronisiert und durch Rename ersetzt. Der bisherige Stand bleibt bis dahin
erhalten. Dateien erhalten zunächst private Rechte (umask 077); Leserechte/ACLs
für den eigenen SMB-Benutzer gezielt passend setzen, niemals pauschal öffentlich
machen. Der Browser enthält auch historische Prognose-/Kostenwerte: vertraulich
behandeln, obwohl Secrets und Standort-/Gerätenamen ausgefiltert werden.

## Gespeicherten Modellvergleich optional verwenden

Ohne vorliegenden Referenzvergleich bleibt `Modellvorteil: Nicht belegt`.
Der normale Dashboardexport rechnet weder Baseline noch GENETIC-Wiedergabe neu.
Ein schon privat vorhandener Economics-Report aus `economics_report` kann als
**vierter** Wrapperparameter angegeben werden:

```bash
/bin/bash /mnt/user/appdata/ems-dashboard/tools/unraid-ems-dashboard.sh \
  /mnt/user/appdata/ems-dashboard/tools/ems-dashboard.pyz \
  GEPRUEFTER_BUNDLE_SHA256 /mnt/user/private-ems-dashboard \
  /mnt/user/appdata/ems-dashboard/private-economics-report.json
```

Akzeptiert werden nur passende originale Lösungsbytes und Projektionshashes,
versionierter gepinnter nativer Engine-Nachweis, erfolgreicher gespeicherter
Replay, identische Eingaben/Endwertkurve und konsistente Intervallabrechnung.
Ausgegeben wird die Differenz der endwertbereinigten Referenz-/GENETIC-Kosten,
auch Null oder ein negativer Vorteil. Ein Prozentwert ohne belastbaren Nenner
wird nicht erfunden. Der Report ist ein vertrauenswürdiger privater Diagnoseexport,
keine kryptographisch signierte Fremdevidenz. Die historische Requestbindung wird
separat bewertet; Legacy wird durch einen Modellvergleich nicht aufgewertet.
Vorhandene alte Vergleiche können neue reguläre Pläne nicht automatisch abdecken;
dann steht dort wieder `Nicht belegt`, bis ein separat geprüfter Offlinevergleich
vorliegt. Dieser PR erzeugt im regulären Betrieb keinen solchen Vergleich.

## Fehler, Aktualisierung und Rücknahme

- Exit 0: vollständiger aktueller Export; Exit 2: Eingabe ungültig/Sync gerade
  gesperrt, letzte gültige Daten mit sichtbarem Fehlerbanner. Ein überlappender
  Wrapperjob beendet sich ohne neue Arbeit.
- Laufzeit-/Transportfehler nach Beginn des Exports: letzte gültige Datei bleibt
  erhalten, sichtbares Transportfehlerbanner. Fällt der komplette Scheduler aus
  oder scheitert bereits die sichere Container-/Pfad-/Hashprüfung, warnt die Seite
  spätestens nach drei Minuten anhand der letzten erfolgreichen Prüfzeit.
- Fehler vor dem allerersten gültigen Export: Python-Leser erzeugt eine leere
  Fehleransicht; fehlt sogar die sichere Python-Ausführung, entsteht keine gültige
  Erstansicht. Exitstatus/privates Schedulerlog prüfen.
- Keine Originale reparieren, neu hashen, Rechte rekursiv ändern, Prozesse stoppen
  oder einen Testlauf auslösen. Erst bei einem späteren regulären gültigen Stand
  verschwindet die Fehlermarkierung automatisch.
- Rücknahme: nur den eigenen Lesejob im verwendeten Scheduler deaktivieren und
  private Dashboard-Werkzeuge/Anzeige nach Bedarf archivieren. Der Helfer läuft
  unabhängig weiter; keine Produktionskonfiguration zurücksetzen.

## Linux ohne Unraid

Mit vorhandenem Python 3.11+ und Zeitzonendaten kann derselbe Leser direkt laufen:

```bash
python3 -I -B /PRIVATE/ems-dashboard.pyz \
  --source /READ_ONLY/helper-output --destination /PRIVATE/dashboard
```

Optional `--economics /PRIVATE/existing-economics.json`; für nachweislich bekannte
alte Mitternachtsraster `--legacy-timezone Europe/Berlin`. Diese Angaben erzeugen
keine fehlenden historischen Quellenbelege. Auch hier nur den Leser zeitgesteuert
aufrufen, keinen zusätzlichen Helfer.

## Abnahme vor Aktivierung

Synthetische Desktop-/Mobil-/Historien-/Fehleransichten sind im
[Reviewbericht](DASHBOARD_REVIEW.md) verlinkt. Private Prüfpunkte:
ursprünglicher Sync-State samt Lösungen, reale Zuordnung zum letzten erfolgreichen
Lauf, Originalwerte 29.–31.10., geschützter Dateizugang, reguläres Ereignis ohne
Zusatzlauf, atomare Aktualisierung, letzte gültige Anzeige nach ungültiger Kopie,
Scheduler-/Browseraktualisierung und Abschalten nur des Lesers.

Der Originalinhalt vom 30.10. und der zugehörige Sync-State waren über den früher
verfügbaren privaten Pfad nicht lesbar. Der Existenznachweis ersetzt diese Abnahme
nicht. Keine synthetische Datei als echte Tageslösung und keinen selbst erfundenen
`succeeded`-Claim verwenden. Die gemeinsame vollständige private Unraid-Abnahme
und die notwendigen Reviews bleiben deshalb ausdrücklich Voraussetzung für eine
spätere Aktivierung.

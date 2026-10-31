# Phase 1: vorhandene GENETIC-Pläne lokal öffnen

**Erweiterung im separaten Phase-2-Review:**
[Wirtschaftlichkeitsvergleich und private Offline-Abnahme](ECONOMICS_COMPARISON.md).
Die folgenden ursprünglichen Phase-1-Aussagen beschreiben PR #14. Im Phase-2-Branch
zeigen die drei Kostenkarten entweder einen nachgewiesen reproduzierten nativen
Modellvergleich oder „Nicht berechenbar“. Das alte Produktionsimage wird dafür
nicht erweitert; es kann einen numerischen, bereinigten `--comparison-inputs`-
Export rein lesend liefern. Berechnung auf dem Diagnose-Rechner, niemals per
Optimierungs-API. Neue Bundle-/Wrapper-Hashes stehen in der Phase-2-Dokumentation;
alte Phase-1-Hashes gelten ausschließlich für deren alten Bundle-Stand.

Review-Werkzeug für Issue #6, eigenständiger PR auf Main. **Keine Phase-2-Simulation,
keine neue Optimierung, keine Geräteansteuerung und kein Webserver.** Bestehender
Helfer, Container, Ports, Betriebsarten und Konfiguration bleiben unverändert.
Dieser Auftrag hat keine Produktionsdateien gelesen oder Reports auf Unraid erzeugt.
Die reale Betreiberprüfung der vorhandenen zwei Pläne steht noch aus.

## Was die Ansicht zeigt

- Alle vorhandenen `solution-<version>.json` und gültigen Claim-Versionen sind
  auswählbar, auch bei aktuellem `waiting-publication`. Erfolgreicher Claim,
  fehlende/defekte Lösung und fehlende Zuordnung sind getrennte Zustände.
- Zeitachse, Tabelle und anklickbare Slot-Details für AC-/DC-Ladefaktoren,
  Entladefreigabe, Batterieexport und EV-Faktoren, soweit tatsächlich gespeichert.
  Geräte-Starttermine, Modell-Belegung und Tail-Diagnostik werden separat gezeigt.
  Gerätenamen werden konsistent innerhalb eines Plans anonymisiert.
- Originalraster 900/3600 s. Die 15-Minuten-Ansicht einer Stundenentscheidung
  wiederholt **dieselbe** Entscheidung mit derselben Originalindexnummer; sie
  erzeugt keine zusätzlichen Steuerentscheidungen oder aufsummierten Energiewerte.
- UTC-Zeitachse ab tatsächlichem Planstart, lokale Darstellung Europe/Berlin mit
  CET/CEST und explizitem Offset. Beide Herbst-02:00-Stunden sind unterscheidbar;
  im Frühjahr wird keine fehlende Stunde erzeugt. Kein künstlicher Mitternachtsstart.
- `controls_start_at_now=true` bedeutet Laufzeitbezug. Bei älteren Prefix-Arrays
  mit `false` ist eine explizit bekannte Quellzeitzone erforderlich. Fehlt das Flag
  oder die Zeitbasis, bleiben Originalindizes sichtbar, aber keine Zeit wird geraten.
- `ac_charge`/`dc_charge` sind Faktoren, `discharge_allowed` eine Freigabe. Daraus
  wird **keine** kW-Leistung, Netzladung, Energiemenge, Preisursache oder Ersparnis
  abgeleitet. Formulierungen bleiben bei „Freigabe gesetzt“, nicht „Batterie lädt“.
- Vorhandene Modellkosten, Verluste und SoC-Reihen sind ausdrücklich gespeicherte
  Simulationsergebnisse, keine Messung/Rechnung. Terminalwerte werden nicht erneut
  verrechnet. E3/DC-Referenz und zusätzliche Ersparnis bleiben „Nicht berechnet“.

Geprüfte Definitionen des installierten EOS-Vertrags: gepinnter Upstream-Commit
[`8a8cd43`](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/optimization/genetic/geneticsolution.py),
einschließlich `controls_start_at_now`, relativer Steuerfaktoren und result-/control-
Zeitbasis. [Tail-Diagnostik](https://github.com/Akkudoktor-EOS/EOS/blob/8a8cd43a1915668927eda5504b7de039c2e762b4/src/akkudoktoreos/optimization/genetic/tailvalue.py)
ist Lookahead, kein ausführbarer Steuerplan. Unbekannte Parameter, Genom-/Fitness-
Daten und Konfigurationsobjekte werden nicht als Zeitreihen interpretiert.

## Historische Preise und Prognosen

Aktuelle `prices.json`, `soc.json` und `forecast.json` werden **nie** rückwirkend
verwendet oder für die Anzeige gelesen. Ohne Nachweis erscheint sichtbar:
**„Historische Eingabe nicht belegbar“**. Gespeicherte Steuerentscheidungen und
Modellzusammenfassungen bleiben trotzdem sichtbar.

Optional kann `/output/genetic-evidence/<version>.zip` aus Issue #12 zugeordnet
werden. Die unveränderte eigenständige Doctor-Engine aus PR #10 prüft Schema 2,
sieben Originalartefakte, alle Hashes, Event-/Preisversion, SoC-Proof und Preis-/PV-
Zeitachsen. Archivierter Claim und **exakte Lösungsbytes** müssen zum ausgewählten
Plan passen. Erst dann werden die archivierten 15-Minuten-Preise (EUR/Wh → EUR/kWh),
PV-Werte in W und ursprünglicher SoC gezeigt. Kein aktueller Live-Frischenachweis.
Vier-Artefakt-ZIPs, beschädigte/mischende Archive oder vom Reader noch nicht
validierte Verträge bleiben ohne Input-Overlay. Der vorhandene Doctor-Vertrag ist
für 3600-s-GENETIC-Ereignisse geprüft; 900-s-Entscheidungen sind unabhängig davon
ohne erfundene Inputs sichtbar. Issue #12 ist keine Voraussetzung für Phase 1.

## Auslieferung ohne Containerupdate

Ein kleines deterministisches **Code-Bundle** enthält nur Reader, HTML-Renderer,
eigenständigen historischen Validator und Code-Hashmanifest. Keine Daten, Configs
oder Tokens. Python 3.11 samt Standardbibliothek/System-Zeitzonen des bestehenden
Images genügt. `-I -S -B` verhindert Abhängigkeiten vom installierten Helfer und
Bytecode-Dateien. Es wird nichts in den Container kopiert/installiert.

Auf dem Diagnose-Rechner vorbereitet:

- `C:\Users\volke\eos-v010-private\plan-inspector-reviewed.pyz`
- `C:\Users\volke\eos-v010-private\unraid-plan-inspector-reviewed.sh`

Verbindliche SHA256 dieses Review-Stands:

| Datei | SHA256 |
| --- | --- |
| Code-Bundle | `7db2600123edf8d5ffde248cfc36794dc24097cef4eac4cf68b0431a54fb41c1` |
| Unraid-Wrapper | `3a40a965a5a7b83e2c639135b8852814b9dc9daeec1d35d07e08014b200a14ba` |

Bei abweichendem Hash nicht ausführen. Nach einem späteren Code-Review müssen neue
Hashes explizit geprüft werden; keine bewegliche Branch-URL ungeprüft ausführen.
Selbst bauen auf einem Diagnose-Rechner mit Python 3.11:

```sh
python scripts/build_plan_inspector.py --output /PRIVATE/NEW-plan-inspector.pyz
```

Der Builder liest ausschließlich diese Quelldateien und verweigert vorhandene
Ausgabedateien. Normalisierte LF-Dateien, feste ZIP-Metadaten und unkomprimierte
Einträge liefern denselben Bundle-Hash auf Windows und Linux.

## Unraid: erzeugen und im Browser öffnen

Die folgenden Befehle sind Operator-Schritte, hier **nicht ausgeführt**. Kein
neuer SSH-Dienst, SMB-Share, Webserver oder Port muss dafür aktiviert werden.
Bereits freigegebenen privaten Dateitransfer verwenden.

### 1. Neuer privater Arbeitsordner auf Unraid

In der vorhandenen Unraid-Konsole:

```sh
umask 077
workdir=$(mktemp -d /tmp/eos-plan-inspector.XXXXXXXX)
printf '%s\n' "$workdir"
```

Den tatsächlichen Ordner notieren. Die beiden Code-Dateien privat dorthin kopieren.
Beispiel auf Windows, **nur wenn SSH bereits freigegeben ist**; `UNRAID_HOST` und
den Suffix durch tatsächliche Werte ersetzen, keine Credentials ins Kommando schreiben:

```powershell
scp C:\Users\volke\eos-v010-private\plan-inspector-reviewed.pyz root@UNRAID_HOST:/tmp/eos-plan-inspector.ACTUAL/
scp C:\Users\volke\eos-v010-private\unraid-plan-inspector-reviewed.sh root@UNRAID_HOST:/tmp/eos-plan-inspector.ACTUAL/
```

Alternativ denselben Code über einen bereits vorhandenen geschützten privaten
Transferweg bereitstellen. Keine Lösung, Konfiguration oder Datenkopie veröffentlichen.

### 2. Hashes prüfen und rein lesend HTML erzeugen

Zurück in der Unraid-Konsole, tatsächlichen Arbeitsordner einsetzen:

```sh
cd /tmp/eos-plan-inspector.ACTUAL
umask 077
printf '%s  %s\n' \
  7db2600123edf8d5ffde248cfc36794dc24097cef4eac4cf68b0431a54fb41c1 plan-inspector-reviewed.pyz \
  3a40a965a5a7b83e2c639135b8852814b9dc9daeec1d35d07e08014b200a14ba unraid-plan-inspector-reviewed.sh | sha256sum -c -
```

Nur wenn beide Hashes passen, im selben **neuen** Ordner fortfahren:

```sh
set -C
if bash ./unraid-plan-inspector-reviewed.sh ./plan-inspector-reviewed.pyz \
  7db2600123edf8d5ffde248cfc36794dc24097cef4eac4cf68b0431a54fb41c1 \
  > plan.html.partial && ln -- plan.html.partial plan.html; then
  printf 'HTML erfolgreich: %s/plan.html\n' "$PWD"
  sha256sum plan.html
else
  printf '%s\n' 'Abbruch: keine fertige Planübersicht. Fehlermeldung prüfen, keine Quelldateien ändern.' >&2
fi
```

`set -C` und der exklusive Link verhindern Überschreiben. Bei Fehler ist eine
`.partial` kein Erfolg. Der Wrapper erkennt genau einen laufenden Helfer anhand
des vollständigen `.Config.Image`, prüft `/output` und nimmt ein bestehendes
Shared-Lock. Während eines Sync-Writers: später erneut in neuem Ordner versuchen,
keinen Container/Prozess stoppen. Fehlendes Lock wird nicht angelegt.

Nur wenn der gespeicherte Plan ausdrücklich alte Mitternachtsarrays
(`controls_start_at_now=false`) enthält **und** die damalige EOS-Zeitzone bekannt
ist, optional `--legacy-timezone Europe/Berlin` ergänzen. Ohne diesen Nachweis
bleiben diese Indizes absichtlich ohne Zeitzuordnung. Bei aktuellen nativen Plänen
mit `true` ist die Option unnötig. `--json` gibt alternativ denselben bereinigten
Datensatz aus; keine schreibenden Optionen oder Refreshes sind vorhanden.

### 3. Private HTML-Datei auf den Rechner holen und öffnen

Mit dem vorhandenen privaten Transferweg `plan.html` herunterladen. Beispiel
PowerShell mit bereits freigegebenem SSH, **neuen** lokalen Dateinamen wählen:

```powershell
$planReport = 'C:\Users\volke\eos-v010-private\plan-UNIQUE.html'
if (Test-Path -LiteralPath $planReport) { throw 'Neuen privaten Dateinamen wählen' }
scp root@UNRAID_HOST:/tmp/eos-plan-inspector.ACTUAL/plan.html $planReport
if ($LASTEXITCODE -ne 0) { throw 'Privater Transfer fehlgeschlagen' }
Get-FileHash -Algorithm SHA256 $planReport
Start-Process -FilePath $planReport
```

Den Hash mit Unraid vergleichen. Die Datei öffnet direkt im Browser, funktioniert
offline und bietet Planauswahl, Zeitleiste, Slot-Klicks und Rasterumschaltung.
Es gibt bewusst keine `http://UNRAID:PORT`-Adresse. Nicht ins öffentliche Unraid-
Webroot legen und keinen ungeschützten Server starten. `/tmp` ist flüchtig;
benötigte private Reports vor Neustart sicher übertragen.

Der Report ist eine **private Momentaufnahme**, keine automatisch aktualisierte
Live-Oberfläche. Für einen neu gespeicherten Plan einen neuen Report erzeugen.
Auch bereinigte HTML/JSON enthalten private Plan-/Modellwerte: niemals nach GitHub,
in öffentliche Shares oder zu externen Visualisierungsdiensten hochladen.

## Grenzen, Tests und weitere Entwicklung

Reader-Limits: 64 Pläne, 672 Quellslots je Array, 8 MB je JSON, 60 MB je Archiv.
Fehlende oder beschädigte Lösungen bleiben als eigene Diagnosen auswählbar, die
anderen Pläne werden nicht verborgen. Unknown-Werte bleiben unbekannt, keine
0-W-/0-EUR-Ersetzung. Ein fehlender Claim wird nicht aus dem aktuellen Report erfunden.

Synthetische Tests prüfen 900/3600 s, Sommer-/Winterzeit, Legacy-Zeitbasis, mehrere
Pläne, Waiting, ungleiche/defekte Arrays, Archive/SHA-Zuordnung, Privacy-/XSS-Canaries,
anonymisierte Geräte, fehlende Dateien und Shared-Lock. Quellbytes und mtimes sind
unverändert; Schreib-/Netzwerkversuche werden in Tests blockiert. Zusätzlich echte
Container-Tests mit dem unveränderten Produktions-Digest `7e957da3…` und privaten
Kandidaten, ohne installierte Helfer-Module und ohne Source-Mounts; UID 10001,
read-only RootFS, Netzwerk aus. Echter Browser prüft Auswahl, 96/24-Zeilenwechsel,
Details und null externe Seitenanfragen. Keine Optimierer-Tests ausführen:

```sh
pytest -q -m 'not genetic_execution'
```

Der Datenreader und sein bereinigtes JSON sind die spätere Integrationsgrenze für
Wizard #5. Kein zweiter Dauer-Webservice. Phase 2 (Referenzsimulation, End-SoC-
Fairness, zusätzliche Ersparnis oder Ist-Vergleich) ist ausdrücklich nicht implementiert.
Private reale Sichtprüfung auf Unraid und unabhängiger Review bleiben offen;
kein Merge, Deployment, Release oder Image-/Quellen-Publishing durch diesen Auftrag.

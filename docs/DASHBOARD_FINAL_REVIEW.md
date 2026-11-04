# EMS Dashboard v1.0 – Abschlussprüfung R24-01 bis R24-04

Datum: 04.11.2026. Basis: PR #24 `6af922e4e38bb12d49acbaf02bee0b1fd2da27db`
und technischer Gegenreview `5ccacd98644c167da245b42ea043cb2be29080f1`.
Korrekturbranch: `dashboard/ems-v1-final`, eigener gestapelter Korrektur-PR gegen
`dashboard/ems-v1`. Keine Änderungen an den bestehenden Basisbranches.

**Technische Vorbereitung für die gesonderte private Unraid-Abnahme: PASS.**
**Produktive Aktivierung / private Live-Unraid-Abnahme: BLOCKED bzw. noch offen.**
Es wurde auf Unraid nichts geändert oder ausgeführt. Der 30.10. bleibt bis zu
seinen Originaldaten offen; er ist keine Voraussetzung für die ausdrücklich
beauftragte Prüfung der vorhandenen Originale vom 29./31.10.

## Abnahme der vier Befunde

| Befund | Ergebnis | Korrektur / Nachweis |
| --- | --- | --- |
| R24-01 | **PASS** | Separater versionierter Offline-Replay-Sidecar; vollständige Hash-/Parameter-/Enginebindung, geprüfte Herkunftspfade, interne Energiebasis, Fenster und interne Vollzyklen. Reader zeigt grün/blau/orange und kennzeichnet nachträglich berechnete Modellflüsse. |
| R24-02 | **PASS** | SoC exakt am Originalintervallanfang; kein erfundener interpolierter Zustand an einem abgeschnittenen historischen Teilintervall. Stunden- und Viertelstundenraster über beide Zeitumstellungen im echten Browser geprüft. |
| R24-03 | **PASS** | Skala berücksichtigt die gesamte gestapelte PV-/Netz-/unbekannte Ladung. Regression mit 1000 Wh PV + 1000 Wh Netz bleibt innerhalb der SVG-ViewBox. |
| R24-04 | **PASS** | Leere oder lückenhafte Historie liefert `Nicht belegt` für Lade-/Entladefenster und Vollzyklen. Belegte Nullwerte bleiben von fehlenden Daten unterscheidbar. |

## Replay-Vertrag und Einbindung

Details, Energiedefinitionen und konkrete private Befehle:
[REPLAY_SIDECAR.md](REPLAY_SIDECAR.md).

`replay_export` ist ein gesondertes Offline-Werkzeug. Es liest nur die angegebenen
Originaldateien, prüft deren Bytehash und Änderungszeit vor/nachher und schreibt
einen neuen privaten Sidecar. Vorhandene Ziele und Originalpfade werden nicht
überschrieben. Native Konfigurationsinitialisierung bleibt in einem eigenen
Temporärverzeichnis. Keine neue Optimierung, Baseline oder aktuelle Forecast-
Beschaffung; feste gespeicherte Freigaben und exakt die gespeicherten Inputs.

Die Herkunft wird durch Beobachtung der tatsächlichen nativen PV-/Netzladepfade
erfasst. Instrumentierter und uninstrumentierter Lauf müssen übereinstimmen.
Geprüft werden Original-Vergleichsreihen, Gesamtsummen, Endenergie/-wert und
vorhandene Last-/EV-/Gerätereihen. Der Sidecar bindet die vollständigen Original-
Parameter per Hash und die numerische Modellprojektion gesondert. Native Revision,
Quell-/Tabellenfingerprints und Dependency-Versionen bleiben nachvollziehbar.

Farben und EFC verwenden interne Speicherenergie: Ladung nach internem Ladeverlust
und Entnahme vor internem Entladeverlust. Die dazugehörigen DC-Anschlussenergien
bleiben ebenfalls gespeichert. Die lokale private Browserprüfung vergleicht die
angezeigten Mengen und Vollzyklen unmittelbar mit diesen geprüften Sidecarwerten.
Keine SoC-Nettodifferenz, Freigabe oder pauschale Herkunftsverteilung wird eingesetzt.

Der Runtime-Reader enthält ausschließlich den stdlib-Vertragsvalidator.
Der Exporter ist aus dem transportierten Dashboard-Zipapp ausgeschlossen.
HTML-Refresh und normaler Helferbetrieb führen keinen Replay aus. Falsche passende
Sidecars werden abgelehnt; letzte gültige Anzeige samt Fehlerstatus bleibt erhalten.
Ein neuer regulärer Plan ohne passenden Sidecar erhält keine nachträglich erfundenen
Flüsse. Ein weiterer Offline-Export ist dann separat vorzubereiten.

Die Anzeige benennt die Werte ausdrücklich als **nachträglich berechnete native
Modellflüsse**. Ohne historischen Claim zeigt der Kopf `Replay geprüft` und keine
Erfolgsmeldung eines produktiven Dry-Runs. Bei 7/30 Tagen ist eine ausdrücklich
beschriftete Replay-Modellabdeckung ohne historische Claimbestätigung auswählbar;
die ursprüngliche erfolgreiche Claim-Historie bleibt getrennt erhalten.
Überlappende Modellhorizonte werden nicht doppelt gezählt. Fehlstellen bleiben
sichtbar, Teilsummen werden markiert, fehlende Gesamtfenster/-zyklen bleiben unbekannt.

## Echte private Originale

Die vorhandenen privaten gespeicherten Originalantworten vom **29. und 31.10.2026**
wurden unverändert verwendet. Jeweils 24 Originalstunden; keine Rekonstruktion
fehlender Tagesdateien oder erfundenen Claims. Die native EOS-Revision ist
`8a8cd43a1915668927eda5504b7de039c2e762b4` einschließlich Überlappungstabelle.

Die echten Sidecars wurden auf dem lokalen Review-Rechner erzeugt: Testprozess
als UID 10001, network none, read-only Root und Original-Mounts, keine Geräte-
oder Live-Konfigurations-Mounts. Die native Vorwärtswiedergabe erfüllte die
vorhandenen Prüftoleranzen. Herkunftssumme und interne SoC-Energiebilanz stimmen.

Die Kombination aus echten Originalen und fertigem Sidecar wurde danach mit dem
reinen Zipapp im unveränderten lokalen Produktionsimage gelesen:
`sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`.
Dabei ebenfalls UID 10001, network none, read-only, Capabilities entfernt und
no-new-privileges; kein aktueller Projektquellcode oder Replay-Exporter im Container.
Das ist ein lokaler Kompatibilitätsnachweis, keine neue Live-Inventur von Unraid.

Echter Browser mit privaten Daten: beide Originalpläne, interne PV-/Netz-/Entlade-
energien, Original-SoC-Zeitpunkte, Fenster, EFC, Originaldetails, 24 h/7 d/30 d,
leere Claim-Historie und lückenhafte Modellabdeckung bestanden. Mobilbreite 390 px
ohne Seitenüberlauf; **0 externe Seitenabrufe / 0 Browserfehler**.

Alle echten Sidecars, Energiewerte, Originalhashes, HTML-Dateien und Screenshots
bleiben ausschließlich unter dem ignorierten lokalen `private/`-Verzeichnis.
Es wurden keine privaten Screenshots in diesen PR aufgenommen. Lokale Ablage:
`private/real-release/` (beide Originalpläne, Desktop, Mobil und Historie),
Sidecar `private/real-replays-verified.json`.

## Regression und Sicherheitsgates

- Vollständige native Suite lokal: **672 passed / 3 deselected**.
- Dashboard und R1/R2/R3-/Writer-/Replay-Pipeline als UID 10001, read-only und
  network none: **151 passed**. Der CI-Nachweis des exakten Korrektur-Heads folgt
  im eigenständigen Korrektur-PR.
- Zusätzliche Vertrags-/Exporter-/Wrapper-Gegenproben prüfen neu gehashte falsche
  Inputs, Zeitverschiebung, negative/fehlende Energien, SoC-Bilanz, Herkunft,
  Vollzyklen, Fenster, Engine-/Parameterbindung und alte gültige Anzeige.
- Getrennte native Zeitfälle: 24 Stunden mit 24 Stunden- oder 96 Viertelstunden-
  Originalintervallen, jeweils Frühjahrs-/Herbstumstellung. Echte Browserprüfung
  einschließlich wiederholter/übersprungener Ortszeiten und 1000+1000-Wh-Regression.
- Alter Produktionsimage-Smoke umfasst jetzt einen tatsächlichen Sidecar-Reader-
  Durchlauf ohne installierte neue Helfermodule und ohne native Simulation.
- R1/R2/R3-Tests bleiben verpflichtend. Gemeinsamer historischer Validator,
  Doctor-/Inspector-Vertrag, Sync-/Such-/Gerätecode und bisherige Transporthashes
  sind unverändert. Unabhängige ursprüngliche R1/R2-Gegenprobe: PASS.
- Ruff, Actionlint, Code-/Transporthashes, Shell-/JS-Syntax und Diffprüfung werden
  im Korrekturstand geprüft. Die neuen Codehashes haben ein eigenes verpflichtendes
  CI-Gate und enthalten keine privaten Daten oder Freigaben.

Kleine numerische Summationsunterschiede zwischen Python-Versionen sind unter
festen engen Floattoleranzen erlaubt; semantisch abweichende Summen/Fenster werden
weiter abgelehnt. Bei Testvorbereitung trat ein Rechtekonflikt zwischen lokalem
WSL-Benutzer und UID-10001-Testartefakten auf. Wiederholung mit dem jeweiligen
Testdateieigentümer bestand; produktive Dateirechte wurden nicht geändert.

## Verbleibende Gates und Empfehlung

**PASS:** alle vier technischen Befunde behoben; mit den lesbaren Originalen
bereit für die ausdrücklich gesonderte private Unraid-Abnahme.

**Offen/BLOCKED:** Originaldatei und ursprünglicher Sync-State vom 30.10.; echte
Zuordnung der vorhandenen Originalantworten zu den damaligen NAS-Claims; aktueller
Live-Digest und Dateizugang auf Unraid; abschließender unabhängiger Review und
private Betreiberabnahme. `exact_solver_options_proven=false`, Issue #21 und alle
Geräte-/Deploymentfreigaben bleiben unverändert. Kein Modellvorteil wird ohne
separaten vorhandenen Referenzvergleich behauptet.

Für den ersten später freigegebenen privaten Test genau einmal den geprüften
Reader plus bereits fertig gerechneten Sidecar verwenden. Keine Simulation im
Produktionscontainer und kein Scheduler. Originaltabellen, SoC-Zeiten, Farbenergien,
Fenster und Vollzyklen gegen den Sidecar prüfen. Ein kurzer gemeinsamer SH-Lock
kann einen anschließend startenden regulären Sync verzögern; den Export abseits
seines nächsten erwarteten Triggers durchführen. Bei fehlenden Leserechten oder
beschädigten Daten abbrechen, keine produktiven Dateien reparieren.

**Keine Merges, Releases, Unraid-Änderungen, produktiven Container, Port-/Scheduler-
Änderungen, GENETIC-Suchläufe oder Geräteaktionen durchgeführt.**

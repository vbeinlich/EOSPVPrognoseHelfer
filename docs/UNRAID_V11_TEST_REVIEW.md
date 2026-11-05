# EMS v1.1 Testpaket: lokaler Nachweis, keine NAS-Installation

Geprüfter Image-Quellstand: `546baa63ade70cab20c67a7410575c8d2b8dc667`.
Die Testwerkzeuge liegen in einem getrennten Folge-PR. Kein `src/`-Modul des
Helpers, Workers, Readers oder nativen Exporters wurde verändert.

## PASS

- Helper-Target `evidence-candidate` und Worker-Target `runtime` für linux/amd64
  aus einem sauberen `git archive` genau dieses Commits gebaut und als Docker-TAR
  exportiert. Beide TARs lokal wieder geladen, keine Registry-Veröffentlichung.
- Sämtliche installierten eigenen Python-Module bytegleich zum Git-Archiv.
  Gesamtes natives EOS-Quellarchiv gegen SHA256
  `500975e7ba614db6481e8762b51649dd9e0ad8f226753b7b9fa5cb980f51472e`
  und dessen reguläre Quelldateien gegen `/opt/eos` geprüft. UID/GID 10001,
  Python-/Bibliotheksinventare und Lizenzinventare aus den tatsächlichen Images.
- Tatsächliche Image-Identitäten und TAR-Prüfsummen:
  [UNRAID_V11_TEST_IMAGES.json](UNRAID_V11_TEST_IMAGES.json). Lokale Manifest-ID
  ist ausdrücklich kein nachgewiesener Registry-Digest.
- Vollständige ursprüngliche synthetische Teststrecke gegen die aus diesen TARs
  geladenen Images: regulärer Sync mit einer nativen festen Modellantwort,
  atomarer v2-Commit, automatische Worker-Admission, zwei feste native Replays,
  Sidecar/Katalog und Dashboard-Flüsse. Originale bleiben bytegleich, kein zweiter
  Replay beim Neustart, keine Optimierersuche oder Geräteaktion.
- Gemessen bei 0,5 CPU / 768 MiB: Archivcommit etwa 0,026 s, nativer Worker
  etwa 1,80 s, Prozess-RSS etwa 147–149 MiB. Keine Unraid-Lastmessung.
- Lokaler vollständiger Testbestand: **786 bestanden**, **3 echte Optimierertests
  abgewählt**. Installersimulationen laufen separat im Wegwerfcontainer, nicht
  gegen das Host-Dateisystem: **10 Wechsel-/Rollbackfälle** und 18 Preflightfälle.
  Weitere sechs
  neue native Gatefälle sind im vollständigen Lauf enthalten.
- Reale lokale Docker-Create-API akzeptiert den kopierten Containerpayload;
  vorhandene Volume-Identität, Environment, Kommando und Limits bleiben erhalten.
  Beide Testcontainer wurden nie gestartet. Ein kurzlebiger reiner Unix-API-
  Testclient hatte hierfür Zugriff auf den lokalen Docker-Socket; die tatsächlichen
  Helper-/Worker-Testprozesse erhalten keinen Socket.
- Ruff, bisherige Transport-/Dashboard-/LAN-/Worker-Hashgates erhalten.
  CI-Nachweise für den Werkzeug-Head werden im Folge-PR verlinkt. Die bereits
  grüne [PR-#28-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/42040499694)
  bezieht sich auf den eingefrorenen Image-Quellstand.

## Kritischer Eigenreview der Installationswerkzeuge

Dies ist ein Codex-Eigenreview und ersetzt keinen unabhängig organisierten Review.
Folgende Probleme wurden vor Auslieferung gefunden und korrigiert:

| Befund | Stelle | Schwere | Reproduktion und Korrektur |
|---|---|---|---|
| Timeout-Warten konnte impliziten statt lokalen Docker-Kontext verwenden | `unraid-test.sh:safe_stop` | Hoch | Geschlossene Engine-Simulation verweigert fehlendes `--host`; alle Warteaufrufe jetzt explizit lokal |
| Fehlerbehandlung in Bash-Funktionen konnte ohne `-E` beziehungsweise mit unterdrücktem `errexit` ausbleiben | `safe_stop`, `atomic_config`, `restore` | Hoch | Create-/Start-/Runtimefehler, verlorene Create-Antwort, belegter Lock und partielle TOML-Schreibfehler durchlaufen; explizite Fehlerreturns und vererbter ERR-Trap |
| Spätere manuelle TOML-Änderung durfte nicht beim Rollback verloren gehen | `restore` | Hoch | Drift nach Installation: Abbruch vor Stop/Löschen des neuen Helpers; Drift während Stop: alter Helper ohne Überschreiben wieder gestartet |
| Root-Plan/Inspect durfte nicht an UID 10001 schreibbar übergeben werden | `read_plan`, `prepare_review_input` | Hoch | Master bleibt root 0700/0600, Prüfer sehen ausschließlich bekannte Referenzkopien über read-only Bind; Eigentum/Modi werden kontrolliert |
| Anonyme Volumes dürfen bei Neuanlage nicht leer ersetzt werden | `prepare.py:clone_payload` | Hoch | Reale Docker-API mit anonymem `/output`: existierender Volumename ausdrücklich wiedergebunden |
| Preis-/Versionserfolge aus der manuellen Wartezeit durften nicht am ersten Worker-Wasserzeichen verloren gehen | `verify.py:init_worker` | Mittel | Echte native Gateprüfung: Start ab wirklichem Installationszeitpunkt, bestehender State bleibt bytegleich |
| Kurzlebiger ghcr-Prüfcontainer konnte vom bisherigen Publisher als zweiter Helper gezählt werden | `offline` | Mittel | Prüfer starten mit aufgelöster unveränderlicher lokaler Image-ID; nur der laufende Helper trägt den ghcr-Testtag |

Keine offenen Fehler aus diesen Reproduktionen. Die vorhandenen Grenzen von
PR #27/#28 bleiben bestehen: Hashes sind keine Signaturen/WORM, ein Prozessabbruch
vor vollständigem Ready-Archiv kann fehlende Evidenz hinterlassen, und vollständige
atomare Provenienz sämtlicher GENETIC-Suchoptionen wird vom EOS-Antwortvertrag
nicht geliefert. Die bereits gelesenen Beobachtungen werden nicht als Beweis
unbekannter Suchoptionen ausgegeben. Änderungen der tatsächlichen Modellreihen
werden abgelehnt, nicht mit aktuellen Werten repariert.

Der Build wurde aus der eingefrorenen Quelle durchgeführt; die vorliegenden TARs
sind unveränderlich identifiziert. Die ursprünglichen Dockerfiles binden nicht
sämtliche transitiven Buildabhängigkeiten mit Hashlocks. Eine unabhängig vom
Buildcache bitidentische Neuübersetzung wird deshalb NICHT behauptet. Für diesen
Test die geprüften TARs verwenden; kein neuer umfangreicher Releaseprozess.

## OFFEN / BLOCKED für produktive Freigabe

- Keine Verbindung zu Unraid hergestellt, kein vorhandener Container verändert.
  Die FUSE-/UID-/0400-/fsync-Ergebnisse und die bestehende Rollback-TAR mit SHA256
  stammen vom Betreiber und wurden hier nicht als eigene NAS-Prüfung ausgegeben.
- Das Installationsskript prüft bei seiner späteren manuellen Ausführung die
  Betreiber-TAR-Prüfsumme und sichert die tatsächlich benötigten gemounteten
  Dateien. Die Wiederherstellbarkeit dieser bestehenden NAS-TAR ist noch separat
  abzunehmen. Der normale Rollback nutzt den erhaltenen alten Container.
- Tatsächliche Konfigurations-/Runtimeprüfung auf dem NAS, der nächste reguläre
  GENETIC-Lauf, der Archivtest und die private Lastprüfung stehen aus.
- Den genauen bisherigen `--replays`-Pfad für den historischen Import übernehmen.
  Die bestehende Publisher-Zeile vor der manuellen Umstellung sichern. Kein neuer
  Minutenplan, kein automatischer Editor für User Scripts oder Unraid-XML.
- Unabhängiger Gegenreview und ausdrückliche produktive Betreiberfreigabe bleiben
  offen. Erfolgreiche CI ist keine Produktivfreigabe.

[Kurze manuelle Installation, Funktionstest und Rollback](UNRAID_V11_TEST.md).

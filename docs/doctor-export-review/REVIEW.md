# Unabhängiger Doctor-Review – 31.10.2026

PR #10 baut auf PR #9 auf. Kein automatischer Merge und keine reale private
Doctor-Abnahme durch die synthetischen Tests.

## Vollständige unveränderte Originale

| Lokale Datei / vollständige Kopie | SHA256 der Originalbytes |
| --- | --- |
| [DOCTOR_OPERATOR_STEPS.md](local-originals/DOCTOR_OPERATOR_STEPS.md) | `98111e0abbbe95260b7f63e567d68117b7fe5e00c7be8fff45f64bca739e24a9` |
| [unraid-doctor-export.sh](local-originals/unraid-doctor-export.sh) | `5749ecd60abb1fc627ad1126bdafd1c21b41138ba2054565bfb2d5a256029fb6` |

Originale bytegleich, keine Messdaten oder Zugangsdaten. Nur Reviewmaterial.
Für Ausführung die [neue Operator-Anleitung](OPERATOR_RUNBOOK.md) verwenden.

## Produktionsbefund und Ursache

Betreiberbefund: `event.status=waiting-publication`, kein `event.version`,
`errors={}`, zwei erfolgreiche Claims und passende Lösungen; Lock und Konfiguration
verfügbar. Das widerlegt die früheren Erfolge nicht. `sync_once` überschreibt
Report, Preise, SoC und PV-Dateien; nur Claims/Lösungen sind pro Event versioniert.
Der alte Vorabtest setzte voraus, dass der neueste Report den Erfolg noch enthält.
Nur diese Prüfung zu entfernen würde alte Lösungen mit heutigen Eingaben verbinden.

## Korrektur und Beweisgrenze

- Container-Erkennung unverändert über vollständiges `.Config.Image` und
  `.State.Running`, genau ein Treffer; keine Container-/Imageänderung.
- [Historische Engine](../../src/eos_pv_helper/historical.py) bytegleich eingebettet
  und SHA256-geprüft; `python -B -c` im vorhandenen Interpreter, keine Installation,
  kein Download und keine Bytecode-Dateien.
- Normaler Pfad verlangt vollständige unveränderte Eingaben des ursprünglichen
  Erfolgszyklus. Spätere Reports mit alter Event-Version reichen nicht: ihr Zeitbezug
  bzw. SoC-Lesebeweis gehört nicht mehr vor den gespeicherten Dispatch.
- Historischer Pfad verwendet einen vorhandenen vollständigen Schema-2-Snapshot
  und dessen konkrete Event-Version. Keine automatische jüngste-Claim-Auswahl,
  keine Nutzung aktueller Preise/SoC/PV als historische Eingaben.
- Sieben Rohartefakte: Erfolgsreport, damaliger State, Preise, SoC, PV-Prognose,
  PV-Prüfbericht und Lösung. Whitelist, Größenlimits, Hashes und Privacy vor Ausgabe.
- Archivierter Claim und aktuelle persistierte Erfolgsversion müssen identisch sein,
  Lösungsbytes exakt gleich. Erneute Preisversionsberechnung und Control-/Tail-
  Abdeckung. SoC-Datei muss zum Erfolgsreport passen; PV-Bericht zu dessen PV-Teil,
  Prognosegrenzen/-anzahl und vollständige 15-Minuten-Zeitachse müssen stimmen.
- Frische am unveränderten Claim-Zeitpunkt: SoC maximal 300 s bzw. strengere Grenze,
  Leseabschluss vor Dispatch, PV-Cache damals gültig. Capture-/Prüfzeit bleiben real.
  Historische Archive werden weder umgepackt noch zurückdatiert.
- Shared-Lock über Einlesen und Validierung; Export nimmt erneut Lock und prüft
  den Stream nochmals. Neue private Ausgaben erst nach erfolgreichem Vorabtest,
  atomare ZIP-Fertigstellung und kein Überschreiben vorhandener Exporte.

**Ohne alte Eingaben eindeutiger Abbruch.** Zwei Claims/Lösungen und alte
Vier-Artefakt-ZIPs genügen nicht. Ein vollständiger damals konsistenter Backup-/
Snapshot-Satz und bestätigte Herkunft sind erforderlich. Das Skript erzeugt keine
verlorene Historie. Hashes belegen Konsistenz, authentifizieren aber weder Herkunft
noch unabhängig den damaligen internen EOS-Speicherzustand.

Der normale Live-Doctor behält seine aktuelle Frischeprüfung. Der neue
`doctor --snapshot` meldet `historical_snapshot`,
`historical_reference_kind=persisted_claim`, `current_freshness_verified=false`.
Die zusätzliche Betreiberfreigabe für historische Releasebelege bleibt erforderlich.

## Quellstand und Validierung

Ausführbarer Review-Commit: `f8e5eee707c90c70c538fa6ac00f1272cd5bf8cf`.
Wrapper-SHA256: `c15b4d100af653187b39f29ac122beb0ef67fd0735813a50fe5347307dfe7952`.
Engine-SHA256 ohne abschließenden Zeilenumbruch:
`90b07b6bf178f4d49f9bdb5ad47373b6a269dfbc0302050a6f713b5952fd514e`.
Die private Kopie `historical-doctor.py` hat genau diesen Engine-Hash.

Der alte Exporter aus `47bd424...` bleibt unverändert, SHA256
`56a950467d27482bf3361c0739f6cccab394dcbe04d3c0238255119d6bbc8ca5`.
Er wird für vollständige neue Abnahmen ersetzt; eingefrorener OCI-Kandidat,
`GENETIC_ACCEPTANCE.json`, Claims und sämtliche Approval-Flags bleiben unverändert.

Tests: synthetische Eingaben, echte Locks, Fake-Docker, gepinnte EOS-Testinstallation.
Abgedeckt: Waiting, mehrere Erfolge, vollständige Historie trotz neuer Live-Eingaben,
fehlende/inkonsistente Preise/SoC/PV, Versions-/Hash-/Lösungsabweichungen, Frische,
Privacy, Lock, Image-Erkennung, eingebettete Bytes und fehlende Schreibzugriffe.
**390 Tests bestanden, 3 echte Optimiererläufe gezielt ausgespart.** Ruff,
Actionlint, Bash-Syntax, Compose und diff-check erfolgreich. Keine neue GENETIC-
Simulation. Zusätzlich Offline-Smoke-Test der neuen Engine im bereits vorhandenen
privaten Diagnose-Image: UID 10001, read-only, Netzwerk aus, nur synthetisches ZIP
und Engine read-only eingebunden; Exitcode 0. Kein Image-Neubau/Update, kein realer
Abnahmebeleg. Endgültige Ergebnisse und CI am PR-Head:
[PR #10 Checks](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/10/checks).
Private Abnahme bleibt bis zum echten vollständigen und geprüften Nachweis offen.

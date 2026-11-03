# PR #22: erneute R1/R2/R3-Gates

Stand 03.11.2026. Integrationsbasis `db5b304e7dca19d175375283cad9775c7735cd2a`,
voriger Gegenreview `1282d77754d29f271e700ec700d52e13c625b75c`.
Separater Korrekturbranch: `release/pr22-contract-fixes`.
Neue Runtime-/Engine-Quellrevision: **`2dee57de836334c585ed4adb393a7e758eacb1d9`**.
Spätere Operator-/Test-/Berichtsergänzungen verändern diese Runtime-Dateien nicht.
Der exakte übergreifende PR-Head und die zugehörigen CI-Links werden zusätzlich in
der PR-Beschreibung festgehalten. Nicht einen alten CI-Lauf für einen neuen Head verwenden.

## Ergebnis und Reviewgrenze

**R1 PASS, R2 PASS, R3 lokal PASS und als verpflichtende Head-CI-Gates eingerichtet.**
Die erfolgreiche finale Head-CI muss vor einer Mergeentscheidung im Korrektur-PR
nachgewiesen sein. Der Stand ist für einen erneuten unabhängigen Review vorbereitet,
keine externe Vier-Augen-Freigabe oder Betreiberentscheidung ist damit ersetzt.
Der unveränderte alte Head `db5b304` bleibt mit den dort reproduzierten Fehlern BLOCKED.

Keine Merges, Releases/Tags, öffentliche Images/Quellenarchive, produktiven
Containeränderungen, EOS-Schreibzugriffe, zusätzlichen produktiven GENETIC-Läufe
oder Geräteaktionen. Keine Claims, Originalarchive oder Messdaten geändert.
Nur lokale isolierte Tests mit synthetischen Daten; keine echte Optimierersuche.

## Technische Korrekturen

- Ein ursprünglicher Request-Beleg im Sync-Report statt einer zweiten Archivierung.
  Payload und Anzahl der API-Aufrufe bleiben unverändert. Erfassung liegt vor den
  abschließenden SoC-Alter-/Slotprüfungen und vor dem dauerhaften Claim.
- Tatsächliche HTTP-Serialisierung über den bestehenden Client zusätzlich mit
  gemocktem Opener geprüft; keine Netzwerkverbindung. Beleg ist gegen späteres
  Mutieren des Requestobjekts getrennt gespeichert.
- SoC und Zielgerät, vollständiger Mitternachts-Preisrequest, laufrelative
  Solver-Preis-/PV-Reihen, Control und Tail, Zeitzone und Offset werden gebunden.
- Der echte gepinnte EOS-Normalisierer bestätigt den Mitternachts-/Run-Versatz,
  einschließlich beider Herbststunden; nur Normalisierung, kein Optimierungsaufruf.
- Alle vier Consumer verwenden denselben versionierten stdlib-Vertrag.
  Beschädigte vorhandene Kontextfelder werden überall abgelehnt. Legacy-Abwesenheit
  ist `legacy_limited`, Exit 2, `accepted=false`, nicht fälschlich vollständig.
- Inspector zeigt Prüfvertrag und Umfang; keine verifizierten Overlays für Legacy.
- Engine, eingebetteter Wrapper und deterministisches Bundle wurden gemeinsam
  erneuert. Keine installierten Module im alten Produktionsimage vorausgesetzt.

[Vollständiger Daten-/Toleranz-/Legacy-Vertrag](INPUT_BINDING_CONTRACT.md).

## Prüfungen und erneute PASS-Gates

| Gate | Ergebnis | Konkreter Nachweis |
| --- | --- | --- |
| R1: fremde Solverwerte trotz neu berechneter Hashes | PASS | Unabhängige Vektoren für SoC, Gerät, PV, Preis, Request, Zeitbasis, Raster, Länge und Zusatzfelder werden abgelehnt |
| R2: identische Bytes / identischer Prüfumfang | PASS | Core, App, Writer und Inspector; dazu eigenständige CLI ohne Site-Packages. Fehler = blockiert, Legacy = explizit eingeschränkt |
| R3: verpflichtende Negativtests | PASS lokal / Head-CI erforderlich | `tests/test_binding_contract.py`, `evidence_vectors.py`, frühere Review-Gegenprobe in CI; keine manuell als grün ausgegebenen Negativfälle |
| Vollständige lokale Suite | PASS | **585 passed, 3 deselected, 58,54 s**; die drei ausgeschlossenen Tests starten echte Suchläufe |
| Non-root-/Read-only-Pipeline | PASS | **64 passed, 17,35 s**, UID 10001, Netzwerk aus; derselbe Aufruf ist neuer CI-Schritt |
| Native Normalisierung | PASS | Drei Tests mit echter EOS-Normalisierung: Frühling und beide Herbststunden, Optimierer-/HTTP-Fail-Hooks |
| Gültige Sonderwerte | PASS | Null-PV, negative Preise, 0/55,999/100 % SoC, begrenzte Floatabweichungen, UTC/IANA-Zeitbasis |
| Keine neue SoC-Lücke | PASS | Verzögerte Belegerfassung um 301 s: kein POST und kein Claim; Erfassungsfehler erzeugt keinen Wiederholungslauf |
| Originale, Versionen, Locks, Crash-/Privacy-Verhalten | PASS | Bestehende Tests weiter bestanden; kein Backfill, kein Überschreiben, kein geänderter Preis-/Forecastpfad |
| Altes Produktionsimage | PASS | **23 Archiv-Szenarien**, darunter **17 Negativfälle** und Legacy; zusätzlich 6 Doctor-Szenarien und Inspector |
| Eingefrorenes Kandidatenimage | PASS | Dieselben 23 Archiv- und 6 Doctor-Szenarien; unveränderte lokale Kopie, Source-Label `47bd424` |
| Browser | PASS | Fallback-Inspector und Wirtschafts-/Ist-Bericht; 0 externe Seitenabrufe, 0 Browserfehler |
| Lint und Transportintegrität | PASS | Ruff, Actionlint v1.7.7, Compose, JS-Syntax, Diffprüfung; Hashmanifest und aktive Operatorhashes werden in CI geprüft |
| Alte Schutzfunktionen / Defaults | PASS | `simulation_safe`, `verify_solution`, `readback` unverändert; `DRY_RUN`, Write-Gates und Archiv-Opt-in nicht aktiviert |
| Release-/Publishing-Sperren | PASS | Promote, GENETIC_ACCEPTANCE, Kandidatendokument und alter gepinnter Snapshot-Exporter unverändert; keine Freigabe gesetzt |
| Main und PR #22 unverändert | PASS | Main `5688084`, ursprünglicher PR-Head `db5b304`; keine Änderungen an Originalbranches |

Die ursprüngliche Gegenprobe ist als [Vorher-Ergebnis](../review/pr22_contract_probe_result.json)
erhalten. [Nachher-Ergebnis](../review/pr22_contract_probe_result_after.json):
R1/R2 PASS, Core/App lehnen ab, Inspector `unproven`; neuer Enginehash dokumentiert.
Die getrennte Vektorsammlung rehashed absichtlich falsche Artefakte und
Parameterzusammenfassungen, damit der semantische Check selbst geprüft wird.

## Konkrete neue Codehashes

Maßgeblich: [maschinenlesbares Manifest](INPUT_BINDING_TRANSPORTS.json).

| Bestandteil | SHA256 |
| --- | --- |
| Engine-Quelldatei, mit LF | `97c9f3fc19129e9da9ad6990dcbf731e1dd7f3595efd0df360059c46dda0134e` |
| Eingebettete Engine, ohne letztes LF | `4fb311a4ac92f0d8fd37df7fb1746edb76b0ee8cdb85f22641b3a06c94aa30aa` |
| Doctor-Wrapper | `6e1d3c84f5369744f24ba4735a2e39af7338a25bdf30fe7b46e529c836a228d8` |
| Inspector-Codebundle, 104024 Bytes | `d96b7c463cd3e6f6c390c4c152d7cb1f5931e44ce8da6ca9a17aeeb07fad6064` |
| Inspector-Wrapper, unverändert | `aeb5a12796adf8a940c18ac289643e8fd4f54a2cd2e6ec2b1e1861bb4c31c1fd` |

Produktions-Kompatibilität wurde gegen den unveränderten öffentlichen Digest
`7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`
lokal geprüft. In diesem Image gibt es weiterhin kein `doctor.py`/`historical.py`;
die neue Engine läuft mit `-I -S -B`, UID 10001, read-only und ohne Netzwerk oder
Projektquellcode-Mounts. Die ZIPs sind aus dem echten Writer mit ausschließlich
gemocktem Dispatch entstanden. Keine private Messdatei verwendet oder veröffentlicht.

Diese Codehashes sind **keine** neuen OCI-/Inventar-/Quellenarchiv-Freigaben.
Der alte OCI-Kandidat wird weder neu gebaut noch als identisch mit neuem Anwendungscode
behauptet. Späteres Deployment benötigt eigene Prüfung und ausdrückliche Freigabe.

## Weiterhin offene Gates

| Gate | Status | Nächster Schritt |
| --- | --- | --- |
| Issue #21: atomare Runoptionen und No-Device-Vertrag | **BLOCKED / offen** | Separater lesender/offline Vertragsnachweis; `exact_solver_options_proven=false` bleibt |
| Externer unabhängiger Code-Review / Mergefreigabe | **OFFEN** | Neuen exakten Korrektur-Head einschließlich CI und Vektoren prüfen |
| Main-Schutz, Rulesets, Release-Environment | **BLOCKED** | Lesend erneut: Main ungeschützt, 0 Rulesets, 0 Environments; nur autorisierte Administration darf ändern |
| Vollständige private reale Doctor-Abnahme | **OFFEN** | Alte fehlende Metadaten nicht rekonstruieren; später nächsten regulären Erfolg nach gesonderter Aktivierung prüfen |
| Verlustfreie Archivierung in jedem Crashfenster | **OFFEN** | Bekannte Grenze vor dauerhaftem `.ready`; weiterhin fail-closed `evidence_missing`, kein Retry/Backfill |
| Neues Image, Lizenz/Distribution und Deployment | **NICHT FREIGEGEBEN** | Separat prüfen, keine alten Genehmigungen übertragen |
| Geräteausführung | **NICHT FREIGEGEBEN** | Erst #21 und weitere Mess-/Owner-/Betreibergates lösen |

## Sicherer Integrations- und Abnahmeplan

1. Korrektur-PR gegen `release/ems-integration-20261101` unabhängig reviewen;
   `headRefOid` und erfolgreiche CI exakt zusammen prüfen. Kein Auto-Merge.
2. Nur nach Betreiberfreigabe Korrektur in den Integrationsbranch übernehmen.
   Dann den **neuen** Head von PR #22 gegen Main erneut prüfen; nicht den alten
   db5b304-Lauf als neuen Nachweis verwenden.
3. Erst nach weiterer ausdrücklicher Entscheidung PR #22 integrieren. Kein
   automatisches Schließen/Mergen der Original-PRs und kein Release daraus ableiten.
4. Vor einer späteren privaten Abnahme nur den gepinnten neuen Wrapper samt
   [aktiver Operator-Anleitung](doctor-export-review/OPERATOR_RUNBOOK.md) bereitstellen.
   Vorhandene Archive rein lesend mit Scope/Exitcode auswerten; keine Zeitstempel ändern.
5. Produktives Image, Archiv-Opt-in und Gerätefreigabe bleiben gesonderte Vorgänge.
   Keine Abnahmeoptimierung starten, keine Claims löschen, keine Legacy-Belege nachbauen.

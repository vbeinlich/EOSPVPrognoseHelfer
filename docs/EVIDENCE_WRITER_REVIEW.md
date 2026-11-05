# EMS v1.1 Archivwriter: PASS/BLOCKED und unabhängiger Review

Basis: Draft-PR #27, Head `3f47313e3f95b16aff55d4499768c4e00422a570`.
Native EOS-Revision: `8a8cd43a1915668927eda5504b7de039c2e762b4`.

**PASS:** Implementierung und isolierter synthetischer Übergabenachweis.
**BLOCKED:** Produktivbetrieb bis Gegenreview, Release-/Imageprüfung,
NAS-Dateisystem-/Ressourcenabnahme und ausdrücklicher Betreiberfreigabe.

Der Betreiber hat das Fehlen von ZIPs und passenden Evidenz-/Manifestdateien
unter dem produktiven Output bis Tiefe 5 bestätigt. Das alte unveränderte Image
enthält `evidence`, `historical` und `doctor` nicht. Der neue separate Kandidat
enthält diese Module nachprüfbar; das laufende System wurde nicht geändert.

## Inhalt des Folge-PRs

- Vorhandenen einzigen regulären Sync-Writer beibehalten; vollständige
  Worker-Admission und strukturelle Modellprüfung vor dem atomaren Commit.
- Vor Dispatch festgehaltene Last-/PV-/Preis-/Vergütungsreihen im Manifest binden;
  keine spätere Ergänzung, keine zusätzlichen API-Abfragen oder Suchläufe.
- Planfelder in Folgeticks aus dem ursprünglichen Claim im aktuellen Report
  erhalten. Der dabei gefundene Report-/Claim-Konflikt hätte die PR-#27-Admission
  sonst nach dem nächsten regulären Tick blockiert.
- Unveränderliche 0400-Archive, sieben Originale, fsync und exklusive Hardlinks
  erhalten; Konfliktvergleich über das vollständige validierte Manifest.
- Separater Docker-Target `evidence-candidate` und Hashinventur der tatsächlich
  installierten Module. Defaults/Freigaben bleiben unverändert.
- Native Teststrecke von regulärem Sync über tatsächlichen Writer und zwei feste
  Worker-Replays bis Dashboard; zusätzlich Prüfung mit getrennten installierten
  Images ohne Helper-Quellcode-Mounts.

## Nachweismatrix

| Anforderung | Nachweis |
|---|---|
| Neuer regulärer Erfolg automatisch bis Dashboard | `test_regular_sync_commits_originals_then_real_native_worker_and_dashboard`, Zwei-Container-Smoke |
| Tatsächliche Originalbytes / sieben Artefakte | bestehende Writer-Tests und native Übergabe mit SHA256 pro Original |
| Hashbindung / geänderte Originalbytes | `test_modified_saved_solution_bytes_are_rejected_before_native_job` |
| Vorhandene Modellparameter/Freigaben vollständig | fünf negative Antwortfälle, strukturelle `economics.project` vor Commit |
| Keine aktuellen Ersatzwerte | eingefrorene Eingaben und `test_post_cannot_replace_captured_series_with_new_current_values` |
| Keine still abweichende Last/Vergütung | `test_returned_model_cannot_silently_change_dispatch_load_or_tariff`, rehashte Negativfälle |
| Vollständige Admission aus PR #27 | `test_writer_output_is_accepted_by_unmodified_worker_admission`, vier negative Validatorgates |
| Absturz während des Schreibens | echter SIGKILL vor/nach Ready-Link, ursprüngliche Claims und Lösungen bleiben erhalten |
| Sichere Wiederaufnahme | Ready-Version wird erneut geprüft und nativ akzeptiert; ohne Ready keine Rekonstruktion und kein neuer POST |
| Konkurrierender Leser | angehaltener Commit, kein partielles ZIP, Worker sieht `source_busy`; bestehende Reader-/Katalog-Races |
| Zwei reguläre Versionen | zwei echte native Modellantworten, getrennte Archive/Sidecars, erste Bytes unverändert |
| Kein zweiter Replay / Optimierung | erneuter Sync und Worker-Neustart erhalten Receipt/mtime; native Suche und echte HTTP-Aufrufe gesperrt |
| Original-/Sync-Verträge bleiben erhalten | vollständiger bisheriger Testbestand, unveränderte alte Sicherheits-/Transportgates |
| Produktives System bleibt unverändert | nur neue lokale Testimages und zufällige temporäre synthetische Docker-Volumes; kein Remote-Docker-Endpunkt erlaubt |

Die Modellantwort des isolierten Tests wird über einen geschlossenen HTTP-Stub
aus **einem echten nativen Vorwärtslauf mit festen Freigaben** erzeugt. Es läuft
keine GENETIC-Suche. Der Writer archiviert diese regulär gespeicherte Antwort;
der getrennte Worker führt seine **zwei** nativen Vorwärtsreplays aus. Das ist
ein technischer Nachweis des Datenwegs und kein Nachweis einer produktiven
Optimierung, einer historischen Ausführung oder einer Geräteaktion.

## Ergebnisse und Ressourcen

Lokal **761 Tests bestanden**, davon 22 neue Writer-/Native-Fälle, in 105,76 s.
Die drei markierten echten Optimierungstests bleiben explizit ausgeschlossen.
Die headbezogene GitHub-CI samt synthetischem Containerartefakt wird im PR
aufgeführt. Neue Tests ergänzen sämtliche bisherigen Fälle. Ruff und sämtliche bestehenden Hash-/Review-Gates bleiben
verpflichtend. Es werden keine privaten Originale oder Sidecars in CI verwendet.

Zwei lokale Messungen bei jeweils 0,5 CPU und 768 MiB Containerlimit:
synthetischer Sync inklusive einer nativen Modellantwort 0,75–1,67 s,
eigentlicher Archivcommit 0,03–0,10 s; separater nativer Worker 1,59–2,11 s.
Prozess-RSS jeweils etwa 147–149 MiB. Das sind Entwicklungsrechnermessungen; Unraid-FUSE-I/O, konkurrierende
reguläre Optimierung und langfristiges Archivwachstum sind noch nicht abgenommen.
Der CI-Report enthält die konkrete neue Messung, Codehashes und lokale Image-IDs,
aber keine produktiven Daten oder eine Releasefreigabe.

## Offene Punkte und technische Grenzen

- Unabhängiger Gegenreview dieses PRs und von PR #27, konkret zu Originalbindung,
  Lockreihenfolge, Fehlersemantik, Admission und fehlenden Provenienzangaben.
- Neue Helper-Version separat einfrieren, Abhängigkeiten/Lizenzen prüfen,
  reproduzierbaren Image-/Quellnachweis und Rollback-Digest privat bestätigen.
  CI baut lokal, pusht kein Image und erstellt keinen Release.
- Tatsächliche private Abnahme am nächsten ohnehin regulären Lauf, erst nach
  Freigabe. Unraid wurde weder kontaktiert noch installiert oder umkonfiguriert.
- Hardlinks, Modi und fsync auf dem tatsächlichen Ziel-Dateisystem sowie
  Ressourcenparallelität, Platz und private Aufbewahrung prüfen.
- Ein Abbruch vor vollständiger Ready-Datei kann einen unwiederbringlich fehlenden
  Evidenznachweis hinterlassen. Kein Ersatzlauf und keine Rekonstruktion. SIGKILL-
  Tests ersetzen keine Stromausfallprüfung des NAS.
- EOS kann Konfiguration und Cache während seines regulären Laufs intern ändern.
  Abweichungen zu eingefrorenen Eingaben werden abgelehnt; vollständige atomare
  Suchoptionsprovenienz wird nicht behauptet. EOS selbst bleibt unverändert.
- App-seitiges no-overwrite und Hashbindung sind kein WORM und keine Signatur
  gegen privilegierte Manipulation. Eine Rücknahme des alten fehlenden Nachweises
  ist nicht erlaubt; der 30.10. und ungeklärte historische Claims bleiben ungeklärt.

## Unabhängiges Abnahmeprotokoll, noch offen

| Prüfschritt | Status |
|---|---|
| Gegenreview: Quellhead, Tests, Admission und sieben Originale | OPEN |
| Gegenreview: keine zusätzlichen Suchläufe/APIs/Gerätepfade | OPEN |
| Kandidaten-Digest, Lizenzinventur und altes Rollback-Image gesichert | OPEN |
| Private Dateisystem-/Lastprüfung auf Unraid | OPEN |
| Ausdrückliche Freigabe des bestehenden Helper-Wechsels | OPEN |
| Nächster regulärer Erfolg: finales ZIP, Originalhashes und Claim | OPEN |
| Worker `verified`, Dashboard-Flüsse, nächster Tick ohne Doppelrechnung | OPEN |

[Archivvertrag](EVIDENCE_WRITER_CONTRACT.md) und
[Migration, private Inbetriebnahme, Fehlerpfad und Rollback](EVIDENCE_WRITER_MIGRATION.md).
Produktive Definition of Done bleibt bis zu diesen Schritten ausdrücklich offen.

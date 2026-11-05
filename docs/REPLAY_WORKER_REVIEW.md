# EMS v1.1: PASS/BLOCKED und unabhaengiger Gegenreview

Basis: PR #26 / `f9362f53932594fa37800f1939405d47c9a6365f`.
Native EOS-Revision: `8a8cd43a1915668927eda5504b7de039c2e762b4`.

**Lokale technische Implementierung und synthetische Abnahme: PASS.**
**Produktive Vollautomatik und unabhaengige Betreiberabnahme: BLOCKED.**

Es gab keine Installation auf Unraid, keine Aenderung laufender produktiver
Container, keine GENETIC-Suche, Baseline-Optimierung, Forecast-/Energie-API-Abfrage,
Geraeteaktion, Merge, Release oder Image-Publikation. Die bestehende minuetliche
HTML-Aktualisierung und Nginx wurden nicht veraendert. Die bisherigen Reader-,
Exporter-, Energie- und Transportvertraege bleiben unveraendert.

## Nachweise und konkrete Grenzen

- Lokaler vollstaendiger Bestand mit nativer Engine: **739 Tests bestanden**,
  drei echte Optimierungstests ausdruecklich abgewaehlt, 85 Sekunden Laufzeit.
  Davon 45 neue Worker-/Deployment-/Native-Faelle. Ruff, alle alten Transport-/
  Dashboard-Hashgates, neues Codeinventar und bestehende R1/R2-Vertragsprobe
  bestanden. Die headbezogene CI und ihre Artefakte sind im PR separat aufgefuehrt.
- Die neuen Worker-/Deployment-/Native-Tests umfassen automatische Admission,
  Idempotenz, negative Original-/Claim-/Archivfaelle, Backoff, Prozesslimits,
  Last-good, Katalogkonkurrenz und unveraenderte historische Claims.
- Echte Prozessunterbrechung: Elternprozess wird beendet, nativer Kindprozess
  behaelt flock; zweiter Worker wird abgewiesen; vollstaendiger Kandidat wird
  anschliessend ohne zweiten Replay uebernommen.
- Tatsaechliches Runtime-Image: Docker-Inspect prueft Non-root, no-new-privileges,
  keine Capabilities/Geraete/Socketmounts, read-only Root/Originale, network none,
  CPU/RAM/PID-Limits; zweimaliger Start bestaetigt unveraenderte Originale und
  keinen zweiten nativen Replay. Synthetische Testressourcen werden nur lokal
  angelegt und danach entfernt.
- Private lokale Review-Kopien 29./31.10.: zwei echte neue native Replays,
  gleiche Fluesse/Summen wie die vorhandenen Sidecars, alte Dateien unveraendert;
  zusammen mit einem neuen synthetischen Archivplan drei Eintraege im Katalog.
  Alte Originalclaims bleiben `unmatched`, keine Umwidmung zu historischem Erfolg.
- Herkunft dieser lokalen privaten Kopien bleibt ausdruecklich die bereits in
  PR #26 dokumentierte **hashgleiche Rekonstruktion im Archivwriterformat**,
  kein neuer direkter NAS-Originaldownload. Ihre Bytehashes waren unabhaengig
  vom Betreiber vorgegeben. Private Dateien/Sidecars verbleiben ausschliesslich
  in privaten lokalen Review-Ablagen; CI erhaelt nur synthetische Daten.

## Blockierende produktive Voraussetzung

Das unveraenderte angegebene Produktionsimage
`ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`
wurde als separate lokale Instanz ohne Netzwerk ausschliesslich auf vorhandene
Module untersucht: `evidence=False`, `historical=False`, `doctor=False`.
Es enthaelt den aktuellen automatischen Evidenzarchivwriter nicht.

Deshalb ist privat nachzuweisen, ob eine andere bereits existierende Quelle
finale `genetic-evidence/<version>.zip`-Archive mit dem vollstaendigen v2-Vertrag
bereitstellt. Allein ein erfolgreicher Claim und eine lesbare `solution-*.json`
belegen diesen Vertrag nicht. Ohne diese Quelle kann die Automatik mit dem
unveraenderten Helper nicht sicher aktiviert werden. Der Worker darf dann nur
sichtbar warten/ablehnen. Er erzeugt keine alten Eingaben, wertet keine Claims
auf und startet keinen Ersatzlauf. Ein etwaiger Helper-/Archivierungswechsel
liegt ausserhalb dieses PR und benoetigt eine neue ausdrueckliche Freigabe.

## Verbindliche Testmatrix

| Nr. | Anforderung | Nachweis |
|---|---|---|
| 1 | Neuer regulaerer Archivplan bis Dashboard | `test_new_committed_plan_sidecar_dashboard_and_idempotence`, nativer Container-Smoke |
| 2 | Keine zweite Berechnung unveraenderter Bytes | Native-Receipt-Mtime, zweiter Containerstart |
| 3 | Zwei regulaere Versionen separat | `test_two_regular_versions_append_and_keep_earlier_bytes` |
| 4 | Unvollstaendiger Commit / aktiver Writer | fehlendes finales ZIP, `test_busy_original_writer_cannot_be_processed`, spaeterer Commit |
| 5 | Beschaedigte Originalbytes | `source-bytes` in negativen Admission-Tests |
| 6 | Falscher Quellhash | `test_wrong_candidate_source_hash_is_rejected`, bestehende Replay-Quellfingerprinttests |
| 7 | Widerspruechlicher Claim | `claim` / `report` in Admission-Tests |
| 8 | Fehlende historische Eingaben | `missing-input`, `test_missing_original_input_cannot_use_live_replacement` |
| 9 | Abweichende native Simulation | `test_real_native_result_mismatch_becomes_rejected` |
| 10 | Unterbrechung / Wiederaufnahme | echter Elternprozessabbruch und Kandidaten-Recovery |
| 11 | Katalogfehler / Last-good | `test_corrupt_catalog_preserves_last_valid_html`, bestehender Publisher |
| 12 | Gleichzeitiger Update / Refresh | Threaded Reader/Worker und Inode-Snapshot-Adaptertest |
| 13 | Kein Netzwerk / Docker-Socket im Worker | Audit-Denial-Tests, Runtime-Guard und echtes Docker-Inspect |
| 14 | Keine GENETIC-Suche | genau zwei instrumentierte Simulationsaufrufe, verbotener Optimizerstub, unveraenderter Exporter |
| 15 | Keine Geraeteaktionen | Netzwerk-/Prozess-Auditsperre, keine Geraete-/Konfig-/Secretmounts |
| 16 | Ressourcen / Timeouts | Docker-Inspect, Kernel-SIGALRM, RLIMIT_CPU/AS/FSIZE/CORE |
| 17 | 24h/7d/30d ohne Doppelzaehlung | neue Konkurrenzregression und unveraenderte Dashboard-/DST-Tests |
| 18 | Historische und neue Sidecars gemeinsam | expliziter Import, privater Katalog aus zwei alten und einem neuen synthetischen Plan |
| 19 | Bruttofluesse / Wirkungsgrade / EFC | unveraenderte Replay-Physiktests, echte Native-Resultate, private Fluss-/Summengleichheit |
| 20 | Keine historischen Erfolgsumetikettierungen | Aktivierungswatermark, `unmatched`-Importtest, privater Claimvergleich |

Alle Tests sind als technische Konsistenzpruefung zu lesen, nicht als Nachweis
damaliger physischer Batterie-/Geraeteausfuehrung. Der 30.10. wird nicht
automatisch umetikettiert. Eine fehlende Archivquelle bleibt eine reale Sperre.

## Ressourcenmessung

Siehe `REPLAY_WORKER_RESOURCES.json`. Ein synthetischer 24-Slot-Replay lief bei
0,5 CPU / 768 MiB Containerlimit in etwa 1,3 Sekunden nativ, maximal ca. 148 MiB
Prozess-RSS. Zwei private lokale Review-Kopien benoetigten etwa 1,7-1,9 Sekunden
und ca. 149 MiB RSS. Das ist keine Messung waehrend eines produktiven GENETIC-Laufs
auf Unraid. Dessen Konkurrenzverhalten und NAS-I/O bleiben privat abzunehmen.

## Offene Punkte und Gegenreview-Protokoll

1. Vollstaendige finale Originalarchive der tatsaechlichen Produktionsquelle
   nachweisen. Im Zweifel BLOCKED belassen; kein Fallback auf aktuelle Dateien.
2. Direkten NAS-Originaltransfer, private Herkunft und Berechtigungen bestaetigen.
3. Unabhaengiger Reviewer prueft den exakten PR-Head, Codeinventar, alle
   Sicherheitsflags, Fehlerfaelle und die native Ergebnis-/Bruttoenergiebasis.
4. Einen ohnehin regulaeren neuen Dry-Run auf Unraid beobachten; genau einen
   Sidecar und den naechsten minuetlichen HTML-Refresh nachweisen. Keine Suche starten.
5. Ressourcen unter gleichzeitigem regulaerem EMS-Betrieb und lokalen LAN-Browser
   pruefen. Keine zusaetzlichen produktiven Schnittstellen ansprechen.
6. Betreiber erteilt danach ausdrueckliche Aktivierungsfreigabe. Keine Freigabe
   wird aus CI, diesem Eigenreview oder alten PR-Aussagen abgeleitet.

Reviewer: **offen**. Gepruefter Head / Datum: **offen**.
Direkte Originalquelle: **offen**. Produktive Aktivierungsfreigabe: **nicht erteilt**.

Konkrete Installations-, Betriebs-, Import- und Rollbackschritte:
`REPLAY_WORKER_UNRAID.md`. Vertrag: `REPLAY_WORKER_CONTRACT.md`.

# Release-Blocker: Ergebnis vom 30.10.2026

Auftrag: Audit-Findings beheben, ohne Merge, Release oder Produktionsänderung.
Alle Arbeiten erfolgen am PR-Branch und isolierten lokalen Docker-Desktop-System.
Kein EOS-Schreibzugriff, keine Gerätebefehle, kein zusätzlicher Prognoseabruf oder
Optimierungslauf; bestehendes Unraid-Template und produktiver Digest unverändert.

## Nachweise je Audit-Punkt

| Punkt | Konkrekte Korrektur / Nachweis | Status |
| --- | --- | --- |
| Main/Preview/Tag veröffentlichen ungeprüft | `test.yaml` ohne Publish-Job, Docker-Login oder `packages: write`; nur Tests, lokaler Build, Inventar-Artefakt | behoben |
| Lizenzreview nicht an konkrete Bytes gebunden | `release_gate.validate_license_review`: Digest + exakter Roh-Inventarhash + Source-Commit + Version + Quellarchivhash/-URL; `publication.promote` prüft das tatsächlich gepullte Image | behoben |
| Parallele/veraltete latest-Promotion | globaler versions-/refübergreifender Workflow-Lock, Versionsvergleich, unveränderliche Versionstags, erneute Prüfung vor Writes und vor latest | behoben für den einzigen verwalteten Publisher |
| Positiv-/Negativtests | freigegebene idempotente Promotion, Dry-run, falsche Bindungen, fehlende Belege, Quellen-/Smoke-Fehler, Registryfehler, verspätete alte Version, Drift auch nach Versions-Write | automatisiert |
| GCC/libquadmath-Quelle unbekannt | `licenses/native-sources.json`: exakte Binär-/SRPM-Hashes, Build-ID und drei identische ELF-Abschnitte; GCC 4.8.5-44.el7 / 8.5.0-26.el8_10.alma.1 | Zuordnung belegt |
| Vollständiges Inventar | 110 Python- und 105 OS-Einträge; 73 OS-Source-Versionen, 235 Quelldateien SHA256-geprüft; weitere native/Daten-Pflichten in `LICENSE_REVIEW.md` | technisch geprüft, keine Freigabe fingiert |
| Quellenangebot fehlte | `source_bundle.py`: separates deterministisches privates Archiv; Promotion verlangt anonym abrufbare, hashgeprüfte versionierte Quellen vor Tag-Writes | Mechanismus implementiert; öffentliche Bereitstellung bleibt gesperrt |
| Doctor-Frische im Export falsch beschrieben | Live-Uhrzeit bleibt streng; `doctor --snapshot` wertet tatsächliche Erhebung aus und meldet ausdrücklich keine aktuelle Frische | korrigiert und getestet |
| Private Vollabnahme | `doctor_snapshot.py`, Shared-Lock, Whitelist, Hashmanifest, sichere Grenzen und gesonderte Provenienzfreigabe; genaue Operatoranleitung | vorbereitet, noch kein echter Vollbeleg |

## Lokale Validierung

- **279 Tests bestanden**, einschließlich nativer gepinnter EOS-Integration,
  historischer Doctor-Fälle und Publishing-Positiv-/Negativtests.
- Ruff, Actionlint 1.7.12, Compose-Validierung und `git diff --check` bestanden.
- Vollimage `eos-source` gebaut; Offline-Unraid-Smoke bestanden, 192 synthetische
  Viertelstunden, read-only/Dry-run-Verträge und Lizenz-/Quellenindizes geprüft.
- Quellenindizes enthalten keine privaten Konfigurationen oder Zugangsdaten.
- Unabhängiger netzloser lxml-Rebuild mit geänderter libiconv erfolgreich:
  exportiertes Versionssymbol `0x7e01` und XML-Parsing im neuen Wheel bestätigt;
  [Prüfumfang und Hash](LICENSE_REVIEW.md#lxml-und-statisch-eingebettetes-libiconv).

Die endgültigen Commit-/CI- und privaten Kandidatenbelege werden nach dem
Code-Commit ergänzt. Ein lokaler Build wird nicht als veröffentlichter Release
ausgegeben; Lizenzfreigabe, Doctor und Betreiberfreigabe bleiben absichtlich offen.

## Verbleibende Gates

1. Vollständigen privaten Doctor-Beleg samt bestätigter Herkunft aus einem ohnehin
   regulären erfolgreichen Event auswerten. `doctor=null` bleibt bis dahin bestehen;
   keine neue Produktionsoptimierung und keine manipulierten Erhebungszeiten.
2. Exakte private OCI-Bytes, Inventar und vollständiges Quellmaterial final prüfen
   und durch benannten Reviewer/Betreiber freigeben. Alle Approval-Flags bleiben false.
3. Nach gesonderter ausdrücklicher Erlaubnis das geprüfte Quellarchiv veröffentlichen,
   anschließend denselben Image-Digest bereitstellen und anonym prüfen. Hier weder
   Quellasset noch neues Image öffentlich hochgeladen.
4. Geschütztes Release-Environment, Main-Schutz und ausschließliche Registry-
   Schreibrechte konfigurieren/verifizieren. Nicht als bereits eingerichtet behauptet.
   `PUBLICATION_ENABLED` nicht aktivieren; `publication.enabled=false`.
5. Review und ausdrückliche Mergefreigabe für den grünen Commit; danach separate
   Erlaubnis für Tag, Promotion und stabilen Release. Ein Squash/Rebase benötigt
   neuen Kandidaten und neues Review, wenn die Source-Revision sich ändert.

Die Registry hat kein portables atomisches Tag-CAS. Der globale Workflow-Lock
schützt verwaltete Läufe; externe Schreiber müssen ausgeschlossen werden.
Fehler nach dem Versions-Write können einen geprüften Versionstag hinterlassen,
bewegen aber kein `latest`. Zustand danach manuell prüfen, kein blinder Retry.

## Empfehlung

Nach grüner CI am aktuellen Commit ist PR #3 technisch für einen Code-Merge
vorbereitet: Ein Main-Merge veröffentlicht kein Image mehr. Die Betreiber-
Mergefreigabe bleibt erforderlich. **Stabiler Release noch nicht freigegeben**:
echter vollständiger Doctor, konkrete Lizenz-/Digestfreigabe, verfügbares
Quellmaterial und Release-Administration fehlen. Issue #1 bleibt abgeschlossen;
#5 und #6 beginnen erst entsprechend der vereinbarten Reihenfolge.

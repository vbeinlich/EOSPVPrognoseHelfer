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

Code-Commit: `ace727721bee97c65e3a84fb626617ae5377c4e4`.
[Push-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41043282811)
und [PR-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41043291298)
jeweils erfolgreich, Jobs `unit` und `eos-integration`; keine Publish-Jobs.
Der nachfolgende Nachweis-Commit ändert ausschließlich diese Dokumentation und
weiterhin gesperrte Freigabemetadaten. Dessen eigene CI bleibt ebenfalls erforderlich.

## Exakt vorbereiteter privater Kandidat

[Maschinenlesbare Hashes](PRIVATE_CANDIDATE_20261030.json), keine öffentlichen Binärassets:

| Artefakt | Nachweis |
| --- | --- |
| OCI-Manifest | `sha256:0681796587a9a79c6af3c067b2004101351c8ebeae018216f199c967abf692d7` |
| Roh-Inventar SHA256 | `222261b5a20a816a335fb2011fccdbb57c20fe34fc08b6f86c6b2e9fc3b6b93f` |
| Privates Quellarchiv SHA256 | `5388ed86ab415765848e108fe105e828b0669b965a332cfc83165546c2210d7f` |
| Quellarchiv | 510.610.853 Bytes, 615 vollständig hashgeprüfte Payloads; Source-/Notice-Abdeckung gegen exaktes Inventar verifiziert |
| Privates OCI-Archiv | 323.190.272 Bytes, alle referenzierten Blobs hashgeprüft |
| Smoke-Zuordnung | Config-Digest und sämtliche Rootfs-Diff-IDs zwischen OCI-Archiv und lokalem Docker-Export identisch; Revision und 192 Intervalle bestätigt |

Die geplante Quellmaterial-URL in `GENETIC_ACCEPTANCE.json` ist ausdrücklich
**noch nicht veröffentlicht**. `approved=false`, `operator_approved=false`,
`doctor=null` und `publication.enabled=false` bleiben unverändert sperrend.
Ein anderer Source-Commit oder Neubau erfordert neues Review; dieser Kandidat
ist ein überprüfbares privates Arbeitsergebnis, keine erteilte Release-Freigabe.

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

# v0.1.0: Restarbeiten parallel zur privaten Doctor-Abnahme

Stand 30.10.2026. Basis-Main `5688084ad3ea7bdc7cd603c09ade65293e8609c7`;
PR #3 und #8 gemergt. [Main-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41073069909)
erfolgreich. Dieser eigene Vorbereitungs-PR wird nicht automatisch gemergt.
Keine Produktionszugriffe, Adminänderungen, Simulationen oder Veröffentlichungen.

## Erledigt

| Auftrag | Konkreter Nachweis |
| --- | --- |
| Main-Schutz und Rulesets | frisch gelesen: ungeschützt, keine Rulesets; [Beobachtung](release-admin/observed-state.json) |
| Sichere Konfiguration | [konkreter Plan](release-admin/security-plan.json), [Einrichtungsschritte](release-admin/ADMIN_SETUP.md), Offline-Validator und negative Sicherheitstests |
| Environment | Main-Branch als einziges Ziel, unabhängiger benannter Reviewer, keine Selbstfreigabe, Admin-Bypass über UI ausschalten; nichts angewendet |
| GHCR | nur ein verwalteter Writer im Workflow; externe Package-Writer mangels Scope nicht lesbar, genaue Audit-/Entzugsschritte vorbereitet |
| Kandidatenintegrität | OCI, Inventar und vollständige Quellen erneut geprüft; [Hashnachweis](release-admin/artifact-verification.json), keine Artefaktänderung/kein Neubau |
| Formale Reviewunterlagen | [Reviewer-Checkliste](release-admin/LICENSE_REVIEW_WORKSHEET.md) und [ausfüllbare Vorlage](release-admin/license-review-template.json), keine Freigabe erteilt |
| Doctor-Wrapper | [Skript](../scripts/unraid-doctor-export.sh), echte Producer-/Shared-Lock-Funktionen in isolierten Fake-Docker/Curl-Prozessen geprüft |
| Fehler/Privacy | falsche Hashes, kaputte ZIPs, fehlende/Symlink-Dateien, mehrere Container, Writer-Lock und erkannte Secret-/Konfigfelder blockieren finale ZIP-Ausgabe; Quelldateien unverändert |
| Ausführung / Offline | [exakte Unraid-/Diagnose-Anleitung](release-admin/DOCTOR_EXPORT_RUNBOOK.md), keine Neuinstallation im bestehenden Helfer nötig |

Geprüfter Wrapper-SHA256:
`6aaa96f93a2bd166671003edc861b59f18d58a8e8fb717b9b789af1d62fc82ca`.
Wrapper-Quellcommit: `0a8d70612d3ff82929c60a924ba346ff28f1a30d`.
Der Wrapper nutzt weiterhin den unveränderten, separat hashgeprüften Exporter
aus `47bd424...`. Kein beweglicher Stand muss ungeprüft ausgeführt werden.

## Testergebnisse und Grenzen

**328 bestanden, 3 gezielt deselected.** Die drei markierten nativen GENETIC-
Ausführungstests werden in Push- und PR-CI dieses Vorbereitungsbranches explizit
ausgenommen. Keine neue GENETIC-Simulation; die bereits gültigen 302 Kandidaten-
Tests einschließlich damaliger Integration werden nicht als neu ausgeführt
ausgegeben. Alle neuen Tests und die lesende native Providerprüfung laufen.
Andere Branches behalten die bisherige Auswahl; ein künftiger erneuter Optimierer-
Test benötigt eine passende Freigabe und ist nicht Bestandteil dieses Auftrags.

Neu geprüft: Wrapper-Ende-zu-Ende mit synthetischen Dateien und echtem Dateilock,
keine Config-/Secret-Canaries im entpackten ZIP, Rohdateien samt mtime unverändert,
atomarer Abschluss ohne finales ZIP bei Fehlern; Admin-Policy-Mutationen und
Bindung der Reviewer-Vorlage an den unveränderten Kandidaten. Kein synthetischer
Test wird als reale Doctor-Abnahme ausgegeben.

Ruff, Actionlint, Compose und diff-check sind erfolgreich. Bash-Syntax wird
zusätzlich über die Wrapper-Prozesstests geprüft. [Push-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41080516612)
und [PR-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41080753173)
am Quellcommit `0a8d706...` sind vollständig grün. Die nachfolgende reine
Dokumentationsergänzung wird vor Reviewbereitschaft separat in
[PR #9](https://github.com/vbeinlich/EOSPVPrognoseHelfer/pull/9/checks) geprüft.
Die CI baut nur isolierte Testimages/Inventarmetadaten, keine Registry-Images.

## Weiterhin zwingend offen

1. Ergebnis der separat beim Betreiber laufenden privaten Doctor-Abnahme,
   vollständige zusammengehörige Artefakte und bestätigte Herkunft. Historische
   Erhebung bleibt von aktueller Frische getrennt; keine Zeiten/Werte rekonstruieren.
2. Autorisierter Lizenzreviewer mit Identität, Zeitpunkt und ausdrücklicher
   Entscheidung über exakt OCI-/Inventar-/Source-/Quellenhash. Vorlage bleibt pending.
3. Ausdrückliche Adminfreigabe, benannter unabhängiger Reviewer und Einrichtung
   von Main/Environment/Bypass-Schutz. Package-Writer durch berechtigten Admin
   einsehen; konkrete unnötige Benutzerrechte konnten ohne Einsicht nicht bestimmt werden.
4. Spätere separate Erlaubnis für öffentlichen Quellasset, Imagebereitstellung,
   manuelle Promotion, Tag und stabilen Release. `PUBLICATION_ENABLED` bleibt aus.

**Vorbereitung abgeschlossen; Release weiterhin gesperrt.** Kein automatischer
Merge, keine Approval-Flags geändert. Die Dateien `GENETIC_ACCEPTANCE.json` und
`RELEASE_0_1_0_CANDIDATE.json` bleiben unverändert. Neue Hilfen sind Repository-
Quellcode; die bestehenden privaten OCI-/Quellenarchive wurden nicht angepasst.
Ein anderer Release-Kandidat würde eine vollständige neue Prüfung erfordern.

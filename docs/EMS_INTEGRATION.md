# EMS: Integrationsstand und Abnahmeplan

Stand 01.11.2026. Review-Vorbereitung, kein freigegebener Produktivbetrieb.
Main bleibt `5688084ad3ea7bdc7cd603c09ade65293e8609c7`.
Alle fünf Original-PRs sind offen; ihre Heads und Einzel-CIs wurden neu geprüft.
[Maschinenlesbare Quellen und unveränderte Freigabekontrollen](EMS_SOURCE_MANIFEST.json).

| PR | Head | Abhängigkeit | Integrierte Verantwortung | Konflikte / Abnahme |
| --- | --- | --- | --- | --- |
| #9 | `d41d6fd` | Main | Release-/Adminvorbereitung und Exporthärtung | Keine Adminfreigabe enthalten; tatsächliche GitHub-Schutzeinstellungen offen |
| #10 | `45ee76c` | #9 | Eigenständiger historischer Doctor, Container-/Exportprüfung | Gemeinsame Engine; Schema 1 bleibt für volle Historie unvollständig |
| #13 | `ea55a67` | Main; fachlich Doctor-Vertrag aus #10 | Einziger Ereignisarchiv-Writer | Opt-in aus; Crash-/Recovery-/Lock-/Privacy-Prüfung erforderlich |
| #14 | `093def1` | Main; liest denselben Doctor-Vertrag | Statischer Plan-Inspector | Keine zweite Prüfengine oder API; Eingaben nur nach nachvollziehbarer Bindung |
| #15 | `814676a` | #14 | Native Offline-Wiedergabe und E3/DC-Referenzvergleich | Keine Suche; Endwerte/LCOS fair behandeln; fehlende Daten bleiben unbekannt |

`historical.py` war in #10/#13/#14 identisch. Wrapper-Einbettung und Code-Bundle sind
Transportkopien derselben geprüften Engine; keine getrennten fachlichen Implementierungen.
Der alte gepinnte `doctor_snapshot.py` bleibt unverändert für Reproduzierbarkeit,
ist aber keine zweite aktuelle Empfehlung für vollständige historische Abnahmen.

## Tatsächliche Integration

Auf `release/ems-integration-20261101` wurden Änderungen **per Patch** übernommen:
erst #9/#10 zusammen, dann #13, dann #14/#15 zusammen. Kein GitHub-Merge, kein
Main-Update und keine Änderung der Original-PR-Branches. Quellcommits werden als
Provenienz dokumentiert; sie wurden nicht künstlich zu Main-Vorfahren erklärt.
Der ursprüngliche Kandidatencommit `47bd424` bleibt über Main erreichbar.

Sieben gemeinsam betroffene Konfliktdateien wurden fachlich aufgelöst:

- `.github/workflows/test.yaml`: alle Doctor-/Archiv-/Inspector-/Browser-Consumer
  erhalten, alter Produktionsdigest nur einmal geladen. Echte Optimierer-Tests
  branchunabhängig ausgeschlossen; Workflowrechte weiterhin `contents: read`.
- `tests/test_no_genetic_preparation.py`: ein gemeinsamer strikter CI-/AST-Schutz.
- `tests/test_snapshot.py`: gleiche Negativprüfung unter einem Namen erhalten;
  Vier-Artefakt-Snapshots nicht nachträglich zu vollständigen Nachweisen erklären.
- `docs/DOCTOR_PRIVATE_ACCEPTANCE.md`: aktuelle Schema-2-Anleitung aus #10 plus
  Verweis auf den einzigen neuen Writer aus #13; keine veraltete Exportanleitung.
- `README.md`, `docs/UNRAID_SETUP.md`: Archiv- und Analysehinweise zusammengeführt.
- `pyproject.toml`: doppelte TOML-Markerdefinition entfernt, genau ein Testmarker.

Die unveränderte kombinierte Ausgangsbasis bestand **508 Tests, 3 deselected**,
bevor neue Provenienz-/Plan-Ist-Funktionen begonnen wurden. Damit wurden die
Phasen bewusst getrennt. Es wurde keine native GENETIC-Suche ausgeführt.

## Ergänzungen nach dem Integrationsgate

1. **Bestehende Archivierung erweitert, keine zweite Archivierung:** dieselben sieben
   Originalartefakte, optionale Producer-Metadaten mit beobachteten sicheren Optionen,
   Hash des tatsächlichen Dispatch-Payloads und Bindung an zurückgegebene Parameter.
   Kein zusätzlicher GET, kein veränderter POST und keine Änderung von Claims,
   Preisverarbeitung, PV-Prognose oder Taktung. Weiterhin standardmäßig deaktiviert.
2. **Nachweisgrenze ausdrücklich:** Die Lösung belegt tatsächliche Eingabereihen,
   Batterieparameter und Endwert. Globale Solveroptionen und Jahreslastwert werden
   im installierten Antwortvertrag nicht atomar als verwendete Laufkonfiguration
   zurückgegeben. Vorher beobachtete 11.251 kWh sind keine atomare Laufbestätigung.
   `exact_solver_options_proven=false`; verlorene Informationen werden nicht ergänzt.
3. **Plan-Ist offline:** [Datenvertrag und Anleitung](PLAN_ACTUAL.md). Keine neue
   Quelle, kein Poller, kein HA-POST, kein Device-Adapter. Messwerte werden strikt
   von Forecast-/Szenariowerten und kausalen Einsparungsbehauptungen getrennt.
4. **LUOX-Abgleich:** reine Offline-Prüffunktion für belegte Vertragsbestandteile.
   Keine zweite Preisquelle und keine erneute Bearbeitung bereits fertiger evcc-Endpreise.

## Erhalt des laufenden Dry-Runs

Zwei Bedeutungen nicht verwechseln: Helfer-`DRY_RUN`/Write-Gates schützen Importe und
Optimizer-Dispatch. EOS-`PREDICTION`, fehlender Adapter und fehlender Webhook schützen
vor Geräteausführung. Ein erfolgreicher regulärer Simulationsbetrieb kann erlaubte
EOS-Import-/Optimierungsschreibzugriffe benötigen, ohne Geräte zu steuern.
**Keine produktiven Flags wurden hier umgestellt.**

Der geprüfte EOS-Handler setzt beim POST intern den Optimierungsmodus. Deshalb
ist `PREDICTION` in der globalen Config allein kein atomarer Nebenwirkungsbeweis;
die bestehenden Adapter-/Notify-Sperren bleiben wesentlich. Die installierte
Request-Schemaform enthält keinen expliziten nebenwirkungsfreien Ausführungsmodus
oder vollständigen Solveroptions-Snapshot. Ein zweiter GET würde diese Lücke nicht
atomar schließen. [Eigenständiges Vertragsgate #21](https://github.com/vbeinlich/EOSPVPrognoseHelfer/issues/21)
bleibt offen, ohne den aktuellen Dispatch oder EOS zu verändern.

Lesend am 01.11.2026 bestätigt: `PREDICTION`, GENETIC, kein aktiver EOS-Adapter,
kein Notify-Webhook, `LoadAkkudoktor` mit 11.251 kWh. Kein Optimierungsendpunkt
aufgerufen. Die bestehende 300-s-SoC-Grenze und geprüfte evcc-Frischeprüfung bleiben
unverändert. Beispielkonfiguration: neue Archivierung aus, Preisfreigabe/Schreiben aus.

## Konkreter Merge- und Testplan – nur nach gesonderter Freigabe

**Weg A: ursprüngliche PRs einzeln.** #9 → #10 (danach Base auf Main) → #13 → #14 →
#15 (danach Base auf Main). Nach jedem Schritt neue Head-/Konflikt-/CI-Prüfung.
Die hier dokumentierten gemeinsamen Auflösungen müssen dabei übernommen werden.
Danach ausschließlich die zusätzlichen Integrations-/Provenienz-/Analyseänderungen
übernehmen, nicht sämtliche importierten Patches nochmals anwenden.

**Weg B: konsolidierter Integrations-PR.** Den gesamten hier geprüften Zustand
über einen normalen Merge-Commit integrieren. Anschließend Original-PRs erst nach
Quellvergleich als ersetzt markieren; nicht automatisch schließen. Importierte
Quell-PR-Commits sind nicht automatisch Vorfahren des Integrationscommits.

**Die Wege sind Alternativen.** Nicht beide blind mergen. Betreiber entscheidet
über Weg und konkreten Head; kein Auto-Merge. Die Empfehlung ist ein gemeinsamer
Review dieses Integrationsstands, bevor über den Mergepfad entschieden wird.

Für beide Wege:

1. Quellen/Heads neu bestätigen, Freigabedateien und Publishing-Sperren vergleichen.
2. Gesamtsuite ohne `genetic_execution`, Ruff/Actionlint/Compose/Syntax und
   echte Consumer in altem Produktionsimage und eingefrorenem Kandidaten.
3. Gemeinsame Kette: Mock-Dispatch → Originalarchiv → Doctor → späteres Waiting →
   Inspector → native feste Freigaben → Referenzkosten → synthetische Ist-Abweichung.
4. Non-root/read-only, Locks/Crashs/Idempotenz/Privacy; keine privaten Daten in CI.
5. Browser mit 0 externen Requests, korrekte Einheiten und sichtbare Datenlücken.
6. Nach Merge weiterhin **kein Deployment** ohne separate Freigabe. Neues Image
   bekommt eigene Digests, Quellen-/Inventar-/Lizenzprüfung; alte Kandidatenfreigaben
   gelten nicht für diesen erweiterten Anwendungscode.

## Produktivgates

G0 Code-/Mergefreigabe; G1 GitHub-Schutz und unabhängige Reviewer; G2 Image-/Lizenz-
und Deploymentfreigabe; G3 getrenntes Archiv-Opt-in und Dateisystemprüfung;
G4 private Abnahme des nächsten ohnehin regulären Ereignisses; G5 Meter-/Tarif-
und Referenzvalidierung; G6 Geräteverträge und ausdrückliche begrenzte Steuerfreigabe.
Alle bleiben Betreiberentscheidungen. Keine zusätzliche Optimierung für eine
Abnahme erzwingen, keine Claims/Bestände zurücksetzen und keine Historie reparieren.

Neu lesend geprüft: Main ohne Branch Protection, Rulesets leer, kein Environment;
`PUBLICATION_ENABLED` fehlt, Workflowdefault read und keine automatische PR-Freigabe.
Keine administrativen Einstellungen geändert. GHCR-Writer/Package-Rechte bleiben
separat durch berechtigte Administration nachzuweisen. Siehe #9/Adminrunbook.

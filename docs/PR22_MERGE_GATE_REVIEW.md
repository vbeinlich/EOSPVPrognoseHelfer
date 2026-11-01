# PR #22: kritischer Merge-Gate-Bericht

Stand: 01.11.2026. Bewerteter Head **`db5b304e7dca19d175375283cad9775c7735cd2a`**,
Main **`5688084ad3ea7bdc7cd603c09ade65293e8609c7`**. Beide unverändert und konfliktfrei.
Reviewbranch: `review/pr22-db5b304`. **Merge-Empfehlung für db5b304: BLOCKED.**

Dies ist ein neuer, gegenprüfender Durchlauf mit synthetischen Negativbeispielen,
kein externer personell unabhängiger Vier-Augen-Review und keine Betreiberfreigabe.
Die vorige Aussage „Review bereit“ wird nicht als Korrektheitsbeweis verwendet.
Auf dem Reviewbranch wurden nur Bericht, Gegenprobe und eine redaktionelle
Zeichenkorrektur angelegt. Keine Runtime-Korrektur als erledigt behauptet;
PR #22 selbst wurde nicht geändert. Keine produktive Optimierung, Geräteaktion,
Unraid-Änderung, Claims-/Lösungsänderung, Merge, Release oder öffentliche Image-/Quellenarchiv-Veröffentlichung.

## 1. Nachweise und Grenzen

- [PR-Head-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41290630950)
  und [Push-CI](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41290597600)
  erfolgreich: Unit 530 passed / 4 skipped, native Integration 544 passed /
  3 deselected, Altimage-Consumer, Docker-Smoke und Browser.
- Neuer lokaler Lauf auf unverändertem db5b304: **544 passed, 3 deselected, 51,65 s**.
  Lokales Docker Desktop, Netzwerk aus, Root-Dateisystem und Source-Mounts read-only,
  ausschließlich temporäre synthetische Konfiguration. Keine Optimierersuche.
- Actionlint v1.7.7, Compose, JS-Syntax und Diffprüfung erneut erfolgreich.
- Zusätzliche Gegenprobe unter UID 10001, read-only/network-none; Socket-Aufrufe
  zusätzlich gesperrt. **Exitcode 2 = zwei reproduzierte BLOCKED-Kriterien**.
  [Probe](../review/pr22_contract_probe.py), [synthetisches Ergebnis](../review/pr22_contract_probe_result.json).
  Diese Probe ist absichtlich außerhalb der regulären Pytest-Sammlung und kein
  bestandener Abnahmetest. Die bestehenden grünen CIs führen sie nicht aus.
- Das eingefrorene Kandidatenimage wurde nicht neu gebaut, geladen oder verändert.
  Bestehende Altimage-Nachweise sind positive Kompatibilitätsbelege; sie prüfen
  die hier neu gefundenen Negativfälle noch nicht.

## 2. Sieben Konfliktauflösungen

| Datei | Gate | Konkreter Befund |
| --- | --- | --- |
| `.github/workflows/test.yaml` | PASS | Vereinigung aller Doctor-/Writer-/Inspector-/Browser-Consumer. Universell `not genetic_execution` in beiden Jobs, Weitergabe ins Test-Docker, Rechte bleiben read-only. Kein Publish-Schritt. Siehe separate Testabdeckungslücke R3. |
| `tests/test_no_genetic_preparation.py` | PASS | Beide Testfunktionen erhalten; branchabhängige Ausnahmen sinnvoll durch universellen Ausschluss ersetzt; drei echte Optimierertests bleiben markiert. AST-Schutz ist kein genereller Sandbox-Beweis. |
| `tests/test_snapshot.py` | PASS | Vier-Artefakt-Snapshot wird bewusst nicht mehr als vollständige historische Abnahme akzeptiert. Zwei alte Funktionsnamen entsprechen der vereinheitlichten Negativprüfung, nicht zwei verlorenen Fällen. CLI-/Live-Frischeprüfungen bleiben. |
| `docs/DOCTOR_PRIVATE_ACCEPTANCE.md` | PASS | Schema-2-/Waiting-Anleitung aus #10 und einziger #13-Writer verknüpft; alte Exportanleitung ersetzt. UTF-8-Banner war redaktionell beschädigt; nur auf Reviewbranch korrigiert. „Gemeinsame Engine“ allein belegt nicht dieselbe Gesamtvalidierung, siehe R2. |
| `README.md` | PASS | Archiv, Inspector und Offline-Vergleich zusammen verlinkt, keine automatische Aktivierung. |
| `docs/UNRAID_SETUP.md` | PASS | Getrennte Opt-in-/Offline-Anleitungen erhalten; kein impliziter Produktivwechsel. |
| `pyproject.toml` | PASS | Genau ein `genetic_execution`-Marker; doppelte TOML-Definition entfernt, bestehende Testpfade unverändert. |

Die Dateien `historical.py` aus #10/#13/#14/#22 sind byteidentisch:
SHA256 `09ab170b23348abb52c9e440a4239fde34202746cda3f324baf8609c4ea4acee`.
Der Transporthash ohne abschließendes LF ist davon verschieden; beide Formen nicht
verwechseln. R1 ist eine geerbte Vertragslücke, R2 entsteht durch die nur teilweise
integrierte neue Producer-Prüfung. Die Konfliktauflösungen allein verursachen diese
Fehler nicht; als Gesamtstand benötigt #22 trotzdem Korrekturen.

## 3. Merge-, CI- und Betriebsgates

| Kriterium | Status | Nachweis / Korrektur |
| --- | --- | --- |
| Exakter Head, Main, konfliktfreier Stand | PASS | Git/GitHub erneut geprüft; keine zwischenzeitliche Headänderung |
| Fünf Quellstände und sieben Konfliktauflösungen | PASS | Quellenmanifest und obige Prüfung; importierte Quellcommits nicht fälschlich als Vorfahren dargestellt |
| Sieben Originale, Hash-/Event-/Preisversions-/Zeit-/Reportbindung | PASS | Bestehende strenge Core-Prüfungen, keine aktuellen Dateien als historische Ersatzquelle |
| Archivierte Eingaben entsprechen tatsächlich zurückgegebenem Solvermodell | **BLOCKED** | **R1**: Hashes und Dateizuordnung reichen nicht für diese semantische Bindung |
| Einheitlicher vollständiger Doctor-/Writer-/Inspector-Vertrag | **BLOCKED** | **R2**: dieselben Bytes werden unterschiedlich bewertet |
| Bestehende Head-CI und lokale Regressionstests | PASS | Zahlen/Links oben; keine gefälschten grünen Ergebnisse |
| CI deckt neue Negativfälle und alle beanspruchten Gates ab | **BLOCKED** | **R3**: R1/R2 fehlen; Actionlint bisher nur lokal, Non-root-Writer-Pipeline kein eigener verpflichtender CI-Schritt |
| Default-Dry-Run, Archiv opt-in aus, unveränderte Geräteguards | PASS | `config.example.toml`; `simulation_safe`, `verify_solution`, `readback` AST-identisch zu Main; vorhandener Payload-/API-Count-Test besteht |
| Keine echte Optimierersuche im geprüften CI-Lauf | PASS | Drei Markierungen/Auswahl, Mock-POSTs, Forward-Replay mit Fail-Hooks; keine zusätzliche produktive Simulation |
| Atomar garantiert nebenwirkungsfreie EOS-Ausführung | **BLOCKED** | **#21**, schon in Main offen; kein neu eingeführter Aktorpfad. Dies ist ein Aktivierungs-/Vertragsgate, keine Behauptung eines beobachteten Gerätefehlers |
| Kein Überschreiben, Locks, Privacy und fail-closed Fehler | PASS | Shared-/Exclusive-Locks, Hardlinks, Hash-/Privacytests, keine Reparatur/Retries alter unsicherer Claims |
| Verlustfreie Archivierung über jedes Crashfenster | **BLOCKED** | Bekannte Verfügbarkeitsgrenze vor dauerhaftem `.ready`, siehe Abschnitt 5; derzeit korrekt `evidence_missing`, keine stille falsche Abnahme |
| Main-/Tag-/Preview-Push veröffentlicht kein Image | PASS | Promote-Workflow unverändert, Dispatch-only; `PUBLICATION_ENABLED` nicht vorhanden; Testworkflow ohne Packages-Write |
| Required Checks und unabhängiger Review technisch erzwungen | **BLOCKED** | Main `protected=false`, Rulesets leer. Administratoraktion, keine Änderung vorgenommen |
| Geschütztes Release-Environment / GHCR-Owner nachgewiesen | **BLOCKED** | Environment fehlt, Package-Writerrechte nicht vollständig nachgewiesen. Veröffentlichungs-, nicht fachlicher Codegate |
| Eingefrorene Freigaben/Kandidat unverändert | PASS | Freigabe-/Promote-/Snapshot-Dateien gegenüber Main unverändert; keine neue Distributionsfreigabe |
| Reale Messdaten-/Referenz-/Ersparnisabnahme vollständig | **BLOCKED** | #16/#17 offen. `realized_savings_eur=null` korrekt; Produktivsteuerung weiterhin gesperrt |

Nicht jedes BLOCKED ist ein Code-Merge-Blocker: R1/R2 und ihre Regressionstests R3
müssen vor einer positiven fachlichen Mergeempfehlung gelöst sein. Administration,
private Abnahme, Crash-Verfügbarkeitsziel und #21 bleiben gesonderte explizite Gates;
sie dürfen durch einen bloßen Code-Merge nicht als erledigt gelten.

## 4. Reproduzierte Findings und notwendige Korrekturen

### R1 — P1: Kein Abgleich gespeicherter Originaleingaben gegen Solverparameter

Betroffen: `historical.py:114`/`:247`/`:340`, `event_context.py:66`.
`event_acceptance` prüft Start, Raster, Freigaben und endliche Gesamtkosten.
`validate` prüft PV-/Preis-Abdeckung, Report-/Claim-Zuordnung und Hashes.
`verify_producer` bindet Parameterzusammenfassung an die Lösung selbst; es prüft
nicht, ob diese Parameter zu den übrigen sechs Originalartefakten passen.

**Ausschließlich synthetischer Befund:** Snapshot-SoC 55 %, zurückgegeben 0 %;
Preise `.0003` versus `.009` EUR/Wh; zurückgegebene PV komplett 0 trotz vorhandener
Tageswerte. Alle Dateihashes und Producer-Zusammenfassungen stimmen. Trotzdem
`accepted=true`, `historical_inputs_complete=true`, App-Exit 0 und
`returned_model_inputs_present=true`.

Dies simuliert versehentlich vermischte, jeweils intern korrekte Zyklen. Es ist
kein Authentizitätsangriff, den ein ungesigniertes Hashmanifest lösen könnte.

Notwendig:

1. Tatsächlich gesendeten sicheren Request reproduzierbar binden; sein derzeitiger
   Digest wird nur auf Hexformat geprüft. Whitelist-Payload oder gleichwertiger
   überprüfbarer Vertrag mit ursprünglicher Zeitbasis, SoC und Preisarray erforderlich.
2. Zurückgegebenen Start-SoC nach **belegter EOS-Integerquantisierung**, Preisreihe
   nach Midnight-/Run-Offset und PV nach belegter Intervall-/Wh-Semantik vergleichen.
   Control und Tail, abgeschnittene Vergangenheit, DST und erlaubte Rundung abdecken.
3. Fehlende oder abweichende Bindung ausdrücklich unvollständig/gesperrt melden.
   Vorhandene ältere Minimalarchive nicht nachträglich zu vollständigen Modellen erklären.
   Claims/Dispatch-Retries und aktuelle Betriebsparameter dabei nicht ändern.
4. PV-/SoC-/Preisfehler einzeln testen; gültige 0-W-PV, negative Preise und legitime
   SoC-Quantisierung positiv testen. Keine künstlichen historischen Ergänzungen.

### R2 — P1: Widersprüchliche Bewertung beschädigter Producer-Metadaten

Betroffen: `doctor.py:192`, `evidence.py:110`, `historical.py:247`,
`plan_inspector.py:128`/`:140` und die daraus gebauten Altimage-Transporte.

Die App und der Writer prüfen `verify_producer`. Die eigenständige Engine und
der Inspector tun dies nicht. Eine Änderung der beobachteten Jahreslast ohne
Anpassung ihres ursprünglichen Hashes führt für **dieselben ZIP-Bytes** zu:

| Consumer | Ist-Ergebnis |
| --- | --- |
| Historischer Core / eigenständiger Export | `accepted=true` |
| Neuer App-Doctor | `accepted=false`, Exit 1 |
| Inspector | Eingaben `status=verified` |

Die Unterscheidung „Core prüft nur sieben Originale, App zusätzlich Kontext“ ist
teilweise dokumentiert und kann eine bewusst abgestufte Fähigkeit sein. Dann darf
der Inspector eine solche Gesamtvalidierung aber nicht uneingeschränkt als
verifiziert ausweisen. Der aktuelle gemeinsame Abnahmevertrag ist nicht eindeutig.

Notwendig: eine kanonische stdlib-Prüfung für **vorhandene** Kontextfelder in allen
Consumern, oder explizit versionierte, überall sichtbare Validierungsscope/-limits
ohne uneingeschränktes `verified`. Echte Legacy-Abwesenheit getrennt von beschädigtem
vorhandenem Kontext behandeln; keine Rekonstruktion. Wrapper, Bundle, dokumentierte
Hashes und Tests im unveränderten alten Produktionsimage/Kandidaten gemeinsam erneuern.
Eine neue Engine ist kein unverändertes altes Prüfarbeleg-Artefakt.

### R3 — P2: Grüne vorhandene CI beweist den erweiterten Vertrag nicht

Die gemeinsame Pipeline baut einen passenden Mock-Rücklauf. Die üblichen Fixtures
haben häufig gar keine vollständigen nativen Parameter; daher entdecken sie R1
nicht. Die echte Altimage-Kompatibilität wird positiv geprüft, nicht mit diesen
negativen Kontext-/Modellwidersprüchen.

Vor Merge: R1/R2 als echte ablehnende Regressionstests in Core, App, Writer und
Inspector sowie Transport-Consumer aufnehmen. Actionlint automatisieren und einen
expliziten Non-root/read-only Test des Writers und der gemeinsamen Pipeline in CI
ergänzen. Vorhandene drei Optimierersuche-Tests weiterhin ausschließen. Die manuelle
Gegenprobe dieses Reviews darf nicht als bestandene zusätzliche CI-Abnahme gezählt werden.

### R4 — administrative Gates und R5 — redaktionelle Korrektur

Branchschutz/Rulesets/Reviewpflicht und `public-image-release` benötigen weiterhin
ausdrücklich autorisierte Administration. Die vorhandene Vorlage mit
`operator_approved=false` wurde nicht angewendet. Keine Sperre wurde umgangen.
Nur der beschädigte UTF-8-Banner der Doctor-Anleitung ist auf diesem Reviewbranch
korrigiert; das ändert keinen Runtime-/Wrapper-/Image-Hash.

## 5. Crash-/Recovery-Vertrag: sicherer Fehler ist nicht vollständige Verfügbarkeit

`sync.py:386` persistiert Erfolg vor `archive_success`. Ein Crash nach gespeichertem
Erfolgsreport, aber vor vollständigem `.ready`, verliert die nur im RAM eingefrorenen
Inputs. Der nächste Tick rekonstruiert sie richtigerweise nicht und startet keinen
zweiten Optimierungslauf. Der vorhandene Test
`test_crash_before_complete_ready_never_retries_or_fabricates_success[report]`
erwartet ausdrücklich `evidence_missing` statt eines Archivs.

Das ist transparentes Fail-closed-Verhalten, keine neue stille Regression. Eine
Garantie „jeder gespeicherte Erfolg hat auch nach jedem Crash einen vollständigen
Nachweis“ ist damit jedoch nicht erfüllt. Vor verpflichtender Aktivierung entweder
dieses Verfügbarkeitsziel ausdrücklich einschränken oder einen dauerhaften
Transaktions-/Stagingvertrag im **bestehenden einzigen Writer** entwerfen und an
allen Crashgrenzen testen. Niemals fehlende alte Berichte aus heutigen Daten bauen.

## 6. #16 und #21 können unabhängig vom Merge lesend fortgesetzt werden

### #16: Ja — ein vorhandener direkter Historienpfad wurde nachgewiesen

Zwei reine GETs der vorhandenen evcc-Energie-/Tarifhistorie lieferten Erfolg.
Die vollständigen Originalantworten bleiben privat; keine IP, Gerätetitel,
Energie-, SoC- oder Tarifmesswerte werden hier veröffentlicht. Dieser Befund
präzisiert die frühere Inventur, die nur Cache-/HA-Zugriff geprüft hatte.

Quellbasis evcc **0.318.1**, Commit `e967a35e789081adc7bbd1a730c355e8a870c3fb`:
`server/http_history_handler.go`, `core/metrics/db_history.go`, `collector.go`,
`accumulator.go`, `db.go`, `tariffs.go`, `core/site.go`.

- Historie liefert kWh-Intervalle und getrennte Gegenrichtung; vorhandene finale
  Tarifslots sind lesbar. Keine neue externe Preisquelle nötig.
- Die Batterie-Laderichtung ist Import aus Batteriesicht; Vorzeichen nicht aus
  Grid-Sicht übernehmen. Hauslast zieht `totalChargePower` ab: Loadpoints dürfen
  weder fehlen noch doppelt addiert werden.
- `home` entsteht durch bestehende Leistungsintegration. Andere Richtungen können
  kumulative Zähler oder Fallbackintegration nutzen. Herkunft je Messpunkt belegen;
  keine eigene historische W→Wh-Rekonstruktion erzeugen.
- `QueryEnergy` rundet auf Wh und exponiert `Recovered` nicht, obwohl die DB diesen
  Downtime-Catchup-Marker speichert. Vollständige API-Zeilen beweisen daher keine
  störungsfreie zeitliche Zuordnung. Ein Export muss diese Qualitätsgrenze auflösen.
- `socTemp` ist ein Slotstartwert, kein bestätigter originaler Messzeitpunkt mit
  Sekundenfrische. Nicht künstlich ans Slotende verschieben oder als neue Messung ausgeben.
- AC/DC-Bezug, Retention, Reset-/Recoveryflags, Zeitbasis/DST und belegte LUOX-
  Vertragsbestandteile bleiben zu prüfen. Keine direkte Kopie einer laufenden
  SQLite-Datei unter Ignorieren des WAL; kein Schema-/Recorderumbau.

Nächster sicherer Schritt: private Antworten mit Originalhashes auf Lücken,
Einheiten und Tarifdeckung analysieren; Source-/Qualitätsvertrag klären, erst dann
einen Normalisierer entwerfen. Merge und HA-Authentisierung sind dafür keine Voraussetzung.

### #21: Ja — Schema und Lock-/Seiteneffektvertrag lassen sich ohne Run prüfen

Ein reiner erneuter OpenAPI-GET bestätigt Version `v0.3.0.dev2602241646141478`:
Request enthält `soc`, `forecasts`, `start_solution`, `start_solution_datetime`;
kein per-Request-No-Device-Flag. SHA256 der privaten Schemaantwort:
`64f2d3021ff5dcf74408cba1421236fd06a50d9d475c6551b51b68a4dffa3b55`.

Gepinnter EOS-Quellstand `8a8cd43a1915668927eda5504b7de039c2e762b4`:
`server/eos.py:2236`, `core/ems.py:303`, `:340`, `:400`, `:540`, `:551`,
`optimization/genetic/configrequest.py`, `optimization/genetic/geneticsolution.py`.

- Der Optimize-Handler erzwingt `OPTIMIZATION`; `PREDICTION` im vorherigen GET
  ist keine Eigenschaft dieser Anfrage. Auch ein PREDICTION-Run aktualisiert
  Adapter vor seiner Rückkehr. Kein solcher Run wurde hier ausgeführt.
- `_run_lock` serialisiert EMS-Runs. Die Config-PUT-Handler verwenden diesen
  Lock nicht; Einstellungen sind kein atomar eingefrorener Request-Vertrag.
- Generationen/Seed werden aus Config gelesen; späterer Notify-Zugriff liest
  wiederum aktuelle Config. Ein zweiter GET verhindert diese Race nicht.
- Nach dem Erfolg folgt ausdrücklich `CONTROL_DISPATCH` und ein weiterer
  `adapter.update_data`-Aufruf (`ems.py:551`). Dies ist mehr als eine aus einem
  Methodennamen abgeleitete Vermutung: `adapter/nodered.py:103` sendet in dieser
  Phase Steuerdaten per POST, Home Assistant veröffentlicht Instruktionszustände.
  `adapterabc.py` prüft `enabled()` gegen die dann aktuelle Konfiguration;
  vorhandene Providerinstanzen werden nicht als dauerhaft deaktiviert eingefroren.
  Ein späterer Config-Wechsel kann daher den vorigen GET-Sicherheitsbefund entwerten.
  Dieser Kontrollpfad wurde hier **nicht ausgeführt**; keine Gerätewirkung beobachtet.
- Die Antwort enthält bereits `parameters`, `terminal_value` und `fixed_seed`;
  Letzteres wird aus `self.fix_seed` in die Lösung übernommen. Diese vorhandenen
  belegbaren Angaben nutzen, nicht pauschal alle Laufoptionen als fehlend bezeichnen.
  `fitness_history` nicht ohne weiteren Quellbeleg in Generationen umdeuten.
- Die Schema-/Versionsgleichheit beweist nicht die Byteidentität des tatsächlich
  installierten EOS-Codes mit dem gepinnten Checkout. Dieser Codeidentitätsnachweis
  sowie vollständiger No-Device-/RunContext-Vertrag bleiben offen.

Nächster sicherer Schritt: Vertrag und reine Mock-Race-/Schema-Negativtests entwerfen,
verwendete gegenüber nur beobachteten Feldern einzeln zuordnen. Kein Optimize-POST,
keine Config-PUTs, keine Adapteraktivierung und kein EOS-Upgrade nötig oder freigegeben.

## 7. Exakte Reihenfolge zum erneuten Review

1. R1/R2 auf separatem Korrekturbranch lösen und R3-Negativtests aufnehmen.
2. Alle veränderten Engines, eingebetteten Wrapper, Bundles, Operator-Hashes und
   Altimage-Consumer neu prüfen. Alte Kandidaten-/Lizenzfreigaben nicht übernehmen.
3. Gesamtsuite, Lint, Compose, Non-root-Writer, beide Browser und Head-CI neu bestätigen.
4. Diesen Gate-Bericht gegen den **neuen exakten Head** aktualisieren. db5b304 bleibt
   bis dahin BLOCKED; eine bloße weiterhin grüne alte CI hebt R1/R2 nicht auf.
5. Gesonderte Operatorentscheidung über Mergepfad und Adminmaßnahmen. Danach
   weiterhin separate Image-/Lizenz-/Deployment-/Archiv- und Gerätefreigaben.

Die lesenden Arbeiten an #16/#21 können sofort parallel erfolgen. Es gibt keine
Freigabe für produktive Optimierungen, Änderungen oder Geräteausführung.

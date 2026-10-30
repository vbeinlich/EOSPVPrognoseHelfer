# Release v0.1.0: Readiness und Freigabevorlage

Stand 30.10.2026. Diese Arbeiten erfolgen ausschließlich im Entwicklungsbranch
`release/v0.1.0-readiness` mit eigenem PR. **Keine Veröffentlichung, kein neuer
Tag, keine Admin-Einstellung und kein produktives System wurden verändert.**

## 1. Tatsächlicher Stand nach dem Merge

| Gegenstand | Nachweis |
| --- | --- |
| Main-/Merge-Commit | `55e1bd801c7956b5141f2f41ccf9c1b7ab93e673` |
| Gemergter PR-Head | `eaf14394d2f00c77b7340ffab4a2c60b1d2000cc` |
| Vollständigkeit | Merge hat eaf1439 als zweiten Parent und denselben Tree `dff3a6ece7191d85da5afca91b19ce2615f72691`; alle PR-#3-Dateien enthalten |
| Main-CI | [41063469358](https://github.com/vbeinlich/EOSPVPrognoseHelfer/actions/runs/41063469358), erfolgreich |
| Issue #1 | closed/completed; reale automatische GENETIC-Abnahme bleibt gültig |
| Veröffentlichungen | bei Prüfung keine GitHub-Releases, keine Git-Tag-Refs; frühere Preview-Images sind keine stabilen Releases |

Der alte private OCI-Kandidat aus `ace7277` ist in Main enthalten. Sein OCI-Archiv,
alle Blobhashes, Konfiguration/Rootfs, Inventar und Quellmaterial wurden erneut
rein lokal geprüft. Er bleibt unverändert und besitzt weiterhin Digest
`sha256:0681796587a9a79c6af3c067b2004101351c8ebeae018216f199c967abf692d7`.
Dies beweist **keine Identität mit einem Neubau**. Wegen der aktualisierten
Release-Dokumentation im Buildkontext wird ein neuer privater Kandidat erzeugt;
nur dessen nachfolgend dokumentierte Bytes kommen für diese Freigabe infrage.

## 2. Neuer privater Release-Kandidat

Der unveränderliche Kandidat wird aus dem abschließenden sauberen Code-Commit
dieses PRs erzeugt. Ein nachfolgender Nachweis-Commit aktualisiert ausschließlich
Dokumentation/Freigabemetadaten, ohne das geprüfte Image erneut zu bauen.
Quellcommit, OCI-Digest, Roh-Inventarhash und Quellmaterialhash werden nach
erfolgreichem Build im maschinenlesbaren Kandidatennachweis ergänzt. Bis dahin
ist dies keine abgeschlossene Kandidatenvalidierung.

Die Bindung wird mit `scripts/candidate_verify.py` geprüft: sämtliche OCI-Blobs,
kanonischer OCI-Manifest-Digest, Docker-Konfigurationsdigest und alle Rootfs-
Diff-IDs sowie tatsächliche Inventarbytes und vollständige Source-/Notice-Abdeckung.
Docker- und OCI-Exporter können verschiedene Manifest-Digests bei identischer
Konfiguration erzeugen. Maßgeblich für die spätere Veröffentlichung ist der
**OCI-Digest**, nicht ungeprüft das Multi-Export-Metadatenfeld.

Reproduzierbarer Verifikationsbefehl auf dem Diagnose-Rechner, ohne Pull/Push:

```sh
python scripts/candidate_verify.py --docker-context LOCAL_DEVELOPMENT \
  --oci /PRIVATE/v010-candidate.oci.tar --image eos-pv-helper:v010-private \
  --source-revision EXACT_SOURCE_COMMIT \
  --sources /PRIVATE/eos-pv-helper-v0.1.0-sources.tar.gz \
  > /PRIVATE/candidate-proof-NEW.json
python scripts/unraid_smoke.py --image eos-pv-helper:v010-private --revision EXACT_SOURCE_COMMIT
```

Der Docker-Kontext muss ausdrücklich ein lokaler Entwicklungsendpunkt sein.
Kein Produktions-Docker-Socket. Build-/Quellarchivverfahren:
[RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md). Ein Rebuild oder geänderter Source-
Commit nach Squash/Rebase benötigt vollständige neue Nachweise und Review.
Ein normaler Merge erhält den Kandidaten-Commit als Main-Vorfahren.

## 3. Tests und Sicherheitsnachweise

| Prüfung | Stand |
| --- | --- |
| Unit-/native gepinnte EOS-Integration | 302 Tests lokal erfolgreich |
| Ruff, Actionlint 1.7.12, Compose | erfolgreich |
| Ungeprüfte Main-/Preview-/Tag-Veröffentlichung | Workflow-Policy sperrt automatische Publisher und zusätzlich mutation-getestet |
| Fehlende Operator-/Lizenzfreigabe, falscher Digest/Inventar | automatisiert abgewiesen, keine Registry-Writes |
| Fehlende/beschädigte/unvollständige Quellen, falscher Redirect, Übergröße | realer Download-/Archivprüfpfad mit synthetischem Transport getestet; keine externen Abfragen |
| Spätes altes Release, Registry-Drift/-Fehler, Idempotenz | automatisiert geprüft |
| Parallele Jobs | gemeinsamer fester workflowweiter Concurrency-Lock; Mutation auf Versions-/Ref-Lock oder Abbruch laufender Jobs wird abgelehnt |
| OCI-Provenienz | vollständiger Verifier plus Positiv-/Negativtests für Blobänderung, fehlende Blobs, falsches Runtime-Image und unsichere Pfade |
| Finaler Image-Build, Offline-Smoke und PR-CI | Belege nach Fertigstellung ergänzen; vor Empfehlung erforderlich |

GitHub garantiert höchstens einen laufenden Workflow je Concurrency-Gruppe;
Reihenfolge wartender Läufe wird nicht für die Sicherheit vorausgesetzt.
[GitHub-Dokumentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
Tests prüfen die Repository-Konfiguration und Entscheidungen, starten aber keine
echte Registry-Promotion oder Deployment-Jobs. Registry V2 bietet kein portables
atomisches Tag-CAS; externe Schreiber sind deshalb ein Administrationsgate.

Keine produktiven oder neuen externen Prognose-/Wetter-/Schwachstellen-API-Abfragen.
Software-Builds verwenden die bereits gepinnten öffentlichen Softwarequellen.
Sicherheitsprüfungen belegen Rechte/Isolation, Dateiintegrität, Veröffentlichungs-
pfade und Secret-Abwesenheit im Repository; keine behauptete CVE-Freiheit.

## 4. Private Doctor-Abnahme

**Offen, keine Freigabe fingiert.** In den zugänglichen privaten lokalen
Diagnoseverzeichnissen fehlen zusammengehörige Sync-/Preis-/Claim-/Lösungsdateien.
Es wurde weder auf Unraid exportiert noch ein Produktionslauf ausgelöst.
`doctor=null` und `historical_snapshot_operator_approved=false` bleiben erhalten.

Operatorbefehle, Snapshot-Whitelist und Herkunftsnachweis stehen vollständig in
[DOCTOR_PRIVATE_ACCEPTANCE.md](DOCTOR_PRIVATE_ACCEPTANCE.md). Erforderlich sind
genau der kanonische Preis-Snapshot, Report/State und die zur Event-Version
gehörende Lösung. Export unter Shared-Lock; keine Zeitstempel ändern, Werte
ergänzen, Reports nachbauen oder Claims zurücksetzen.

Live-Doctor: heutige Uhrzeit, Report ≤450 s und SoC ≤300 s bzw. strengere Grenze.
Snapshot-Doctor: tatsächliche deklarierte Erhebung, unverändert strenge Grenzen,
`current_freshness_verified=false`. Alte Daten werden nicht heute frisch.
Für den Release-Beleg: Exitcode 0, alle Checks wahr, konsistente Version und
vier Artefakthashes, privater ZIP-SHA256 plus bestätigte Erhebungs-/Skriptherkunft.
Nur Operator/autorisierten Reviewer diese Herkunft bestätigen lassen. Ein
anschließend scheiternder echter Doctor macht die Abnahme **BLOCKED**; dann
Ursache rein lesend klären, keinen Erfolg erzwingen.

## 5. Lizenzen, Quellen und formale Freigabe

Eigener Code: MIT. EOS: Apache-2.0. Python, OS, native Bibliotheken und Daten
behalten ihre jeweiligen Lizenzen. [Vollständige Komponenten-/Pflichtenprüfung](LICENSE_REVIEW.md).
Inventare und Pflichten müssen am neuen Kandidaten erneut verglichen werden;
keine automatische Übernahme der alten Inventarhashes.

Quellmaterial umfasst exakte Debian-Source-Versionen samt Patches, zwei passende
GCC-SRPMs, LGPL-/MPL-sdists, lxml/native Relinkquellen, ODbL-Daten/Reader, EOS
und Projektquellen/Buildanweisungen. Der Nachweis zur Änderung/Neueinbindung von
libiconv bleibt gültig; ein neuer unbekannter Binärhash sperrt den Build.
Die separate private Source-Datei ist noch kein öffentliches Quellenangebot.

Nur ein benannter autorisierter Reviewer darf `license_review.approved=true`
mit Name/Zeit und **genau** Source-Revision, Version, OCI-Digest, Roh-Inventar-
SHA256, Source-Archiv-SHA256 und versionierter URL freigeben. Nur der Betreiber
darf `operator_approved`, historischen Herkunftsnachweis und Publikationsfreigabe
erteilen. Kein Werkzeug setzt diese Flags automatisch; alle bleiben false.

Die URL ist zunächst geplant, nicht verfügbar. Vor erster neuer öffentlicher
Image-Verteilung muss dasselbe geprüfte Quellarchiv anonym abrufbar sein.
`publication.py` prüft äußeren Hash und sämtliche erforderlichen Payloads.
Technische Quellenprüfung ist keine eigenmächtige rechtliche Distributionsfreigabe.

## 6. GitHub-/Publishing-Administration

[Rein lesender Audit](RELEASE_ADMIN_AUDIT_20261030.json), keine Einstellungen geändert:

| Einstellung | Tatsächlicher Stand | Notwendige Operator-/Adminaktion |
| --- | --- | --- |
| Main-Schutz | `protected=false`, keine Repository-Rulesets | Settings → Rules → Rulesets/Branch protection: Main schützen, PR/Review sowie erfolgreiche Checks `unit` und `eos-integration` verlangen; Force-Push/Delete und unangemessene Bypässe sperren |
| Environment | keine Environments, `public-image-release` fehlt | Settings → Environments → New environment, genau diesen Namen; Required reviewers, Selbstfreigabe verhindern, Admin-Bypass verhindern, Deployment branches nur Main |
| Aktivierungsvariable | `PUBLICATION_ENABLED` fehlt | Nicht vor Abschluss der übrigen Gates setzen; erst nach expliziter Erlaubnis unter Actions variables auf `true` |
| Workflow-Standardrechte | read; Actions dürfen PR-Reviews nicht selbst genehmigen | beibehalten; nur der geschützte manuelle Promote-Job darf packages:write |
| GHCR-Schreiber | Token ohne read:packages, deshalb unbekannt | Package settings → Manage Actions access / Manage access: nur dieses Repo bzw. nötige verantwortliche Publisher, alte PATs/Workflows/weitere Writer prüfen und entziehen; Token nie ins Repository |

Kein Environment wird von Codex automatisch angelegt. Ein fehlendes Environment
kann beim ersten Deployment ungeschützt entstehen; **nicht** zuerst apply
ausführen und erst danach absichern. Ein einziger Eigentümer kann bei aktivierter
Selbstfreigabesperre nicht zugleich alleiniger Dispatcher und Reviewer sein:
zweite autorisierte Person eintragen oder getrennte verantwortliche Rollen nutzen.

Primärdokumentation: [geschützte Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments),
[GHCR-Zugriffssteuerung](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility).
Nach Einrichtung GET-Audit mit entsprechend berechtigtem Admin wiederholen und
Ergebnis dokumentieren. Ein 403/fehlender Scope ist kein Nachweis sicherer Rechte.

## 7. Spätere Veröffentlichung – ausschließlich nach gesonderter Freigabe

Die folgenden Befehle sind **Vorlage**, hier nicht ausgeführt. Linux/POSIX-Shell
auf Diagnose-Rechner; `EXACT_SOURCE_COMMIT`, Digest und private Pfade durch den
abschließend überprüften Kandidatennachweis ersetzen. Zugangsdaten ausschließlich
über bestehende private Credential-Stores, nie als Klartext in Befehlen/Dateien.

1. Readiness-PR durch den Betreiber prüfen/mergen lassen. Main enthält den
   unveränderten Kandidaten-Commit und die nachfolgenden realen Freigabemetadaten.
   Echten Doctor prüfen, konkrete Lizenzfreigabe und Betreiberentscheidung in
   reviewtem Folge-PR dokumentieren. Erst dann Status `approved`, reale Reviewer-
   Angaben und freigegebene Flags übernehmen; diese Vorbereitung tut das nicht.
2. Admin-Gates aus Abschnitt 6 erfüllen. Tatsächlichen Release-Gate-Lauf und
   Provenienz prüfen, noch ohne öffentliche Writes:

   ```sh
   git fetch origin main
   git merge-base --is-ancestor EXACT_SOURCE_COMMIT origin/main
   python scripts/release_gate.py --version v0.1.0 \
     --image-digest EXACT_OCI_DIGEST --source-revision EXACT_SOURCE_COMMIT \
     --inventory /PRIVATE/final-inventory.json
   ```

3. **Erst nach ausdrücklicher Tag-/Quellen-Veröffentlichungserlaubnis:** neuen
   unveränderlichen Tag anlegen, Source-Archiv zuerst als öffentlichen
   **Prerelease-Asset** bereitstellen. Dies ist bereits eine Veröffentlichung,
   kein privater Test. Die Vorlage erzeugt noch keinen stabilen GitHub-Release:

   ```sh
   git tag -a v0.1.0 EXACT_SOURCE_COMMIT -m 'EOS PV Helper v0.1.0'
   git push origin refs/tags/v0.1.0
   gh release create v0.1.0 /PRIVATE/eos-pv-helper-v0.1.0-sources.tar.gz \
     --repo vbeinlich/EOSPVPrognoseHelfer --verify-tag --prerelease \
     --title 'v0.1.0 – sources / distribution pending' \
     --notes-file docs/RELEASE_0_1_0_NOTES.md
   ```

   URL aus der Freigabe anonym herunterladen, SHA256 und vollständige
   Inventarzugehörigkeit prüfen. Ein Draft-Asset ist nicht anonym verfügbar.
   Falls Tag/Asset bereits existiert: nicht überschreiben, Identität prüfen.
4. **Erst nach gesonderter Image-Bereitstellungserlaubnis:** das geprüfte OCI-Archiv
   mit z. B. Skopeo kopieren, Digest erhalten, niemals neu bauen:

   ```sh
   skopeo copy --all --preserve-digests \
     oci-archive:/PRIVATE/v010-candidate.oci.tar \
     docker://ghcr.io/vbeinlich/eospvprognosehelfer:sha-EXACT_SOURCE_COMMIT
   ```

   Kopieren darf keinen anderen Digest ergeben. Registryzustand nach Fehlern
   prüfen; keine automatischen Schreib-Retries. Mit leerem privaten Docker-
   Config-Verzeichnis anonym exakt `@EXACT_OCI_DIGEST` ziehen und auf lokalem
   Diagnose-Docker offline smoken; kein produktiver Helfer wird aktualisiert.
5. Manuelle Promotion zunächst ohne apply; exakten Plan/Quellenprüfung kontrollieren:

   ```sh
   gh workflow run promote.yaml --repo vbeinlich/EOSPVPrognoseHelfer --ref main \
     -f version=v0.1.0 -f digest=EXACT_OCI_DIGEST -f apply=false
   ```

   Die Pipeline prüft zusätzlich grüne Push-CI der Kandidatenrevision, Main-
   Zugehörigkeit, geschlossene #1 und exakten Versionstag. Erst nach Review des
   Plans und expliziter Promotionfreigabe `publication.enabled=true`, für die
   erste latest-Zuordnung `publication.allow_initial_latest=true` reviewen lassen
   und die zuvor fehlende Repo-Variable kontrolliert aktivieren. Dann:

   ```sh
   gh workflow run promote.yaml --repo vbeinlich/EOSPVPrognoseHelfer --ref main \
     -f version=v0.1.0 -f digest=EXACT_OCI_DIGEST -f apply=true
   ```

   Required reviewer bestätigt im geschützten Environment. Keine zweite
   Registry-Schreibstrecke parallel verwenden. Erfolg und anonyme Pullbarkeit
   von `v0.1.0`/`latest` auf genau denselben Digest nachweisen.
6. **Erst nach stabiler Releasefreigabe** Inventar/Hashnachweise als geprüfte
   Assets ergänzen, Release Notes mit realen Belegen finalisieren und:

   ```sh
   gh release edit v0.1.0 --repo vbeinlich/EOSPVPrognoseHelfer \
     --prerelease=false --latest --notes-file docs/RELEASE_0_1_0_NOTES.md
   ```

   Erst jetzt darf Dokumentation eine tatsächlich veröffentlichte stabile
   Version behaupten. Template-Update benötigt eigenen geprüften Commit und
   gesonderte Installations-/Updatefreigabe; bestehende Container bleiben bis dahin unverändert.

## 8. Rollback und Fehlerfälle

- Vor Writes existieren unveränderliche private OCI-/Quellarchive mit Hashes.
  Bei jedem Gatefehler stoppen; keine Freigabeflags, Zeiten oder Hashes passend machen.
- Vor Registry-Writes sind keine Tags betroffen. Fehler nach Versions-Write können
  einen geprüften Versionstag hinterlassen; `latest` bleibt bei einem Abbruch davor
  unverändert. Registry separat lesen und prüfen, keine Tag-Überschreibung.
- Unveränderliche Versionstags nie wiederverwenden; ältere Version darf latest
  nicht zurücksetzen. Falls veröffentlichter Code fehlerhaft ist, höhere korrigierte
  Version mit eigenen Nachweisen vorbereiten, kein verborgenes Überschreiben.
- Produktiver Helfer ist unverändert auf dem historisch abgenommenen Digest
  `sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`.
  Erst nach separat freigegebenem Update kann der Betreiber denselben früheren
  Digest wieder eintragen. Konfiguration, Cache, Secrets, `sync-state.json` und
  Lösungen erhalten; keine Claims zurücksetzen, keine zweite Instanz mit gleichem Output.
- Release-Prerelease bei Fehlschlag als solcher belassen, keine Stable-Fertigstellung
  behaupten. Vorhandenes öffentliches Quellenangebot für verteilte Bytes erhalten.

## 9. Empfehlung und noch offene Entscheidungen

Die abschließende Empfehlung wird nach Kandidatenprüfung und aktueller CI
eingetragen. **Aktuell keine Releasefreigabe.** Unverzichtbar offen bleiben:
vollständiger echter Doctor samt Provenienz, benanntes Lizenz-/Distributionsreview,
geschütztes GitHub-Environment/Main sowie überprüfte Registry-Schreiber und explizite
Tag-/Quellen-/Image-/Stable-Veröffentlichungserlaubnis. Keine Approval-Flags werden
durch diese technischen Arbeiten selbstständig auf true gesetzt.

Erst nach tatsächlich stabilem, gesondert freigegebenem v0.1.0 folgt #5, danach #6.

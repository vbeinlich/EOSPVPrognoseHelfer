# Merge und erster stabiler MIT-Projektrelease

Stand 30.10.2026. **Kein Merge, kein Release und keine neue Image-Veröffentlichung.**
Reihenfolge: #1-Abnahme → PR #3 → stabiler Release → #5 → #6.
Die [reale automatische GENETIC-Abnahme](GENETIC_ABNAHME.md) ist erfüllt und
Issue #1 geschlossen. Sie ist von der Freigabe einer neuen Binärdistribution getrennt.
MIT gilt für eigenen Code, nicht pauschal für das Containerimage.

## Was ein Push jetzt macht

`test.yaml` führt Tests, native EOS-Integration, lokalen Image-Build und netzlosen
Smoke-Test aus. Pushes auf `main`, Preview-Branch oder `v*`-Tags veröffentlichen
**keine Images und bewegen keine Tags**. CI hat keine `packages: write`-
Berechtigung. Als Actions-Artefakt wird nur das Lizenzinventar bereitgestellt,
kein OCI-/Docker-Binärarchiv. `pr-3` wird nicht mehr automatisch aktualisiert.

`promote.yaml` hat ausschließlich `workflow_dispatch`, standardmäßig
`apply=false`, und läuft nur auf `main`. Er baut oder lädt keine Kandidaten hoch.
Die öffentliche Erstbereitstellung eines geprüften Digests ist ein späterer,
gesondert freizugebender Schritt. Ein Versions-Tag alleine veröffentlicht nichts.

## Merge-Checkliste

- [x] Reale #1-Abnahme und Abschluss dokumentiert, Produktionshelfer unverändert.
- [ ] Aktueller PR-Commit: Tests, native EOS-Integration, Ruff, Actionlint, Compose,
  Docker-Build und Offline-Smoke grün; [Ergebnisprotokoll](RELEASE_BLOCKER_RESULTS.md).
- [ ] Sicherheitsreview und ausdrückliche Mergefreigabe für den konkreten Commit.
  Ein Merge ist keine Veröffentlichungserlaubnis.

Offene Distribution-/Doctor-Gates dürfen nach Abschalten automatischer
Veröffentlichungen getrennt vom Code-Merge bearbeitet werden; sie bleiben
verbindlich für den stabilen Release.

## Konkreten privaten Kandidaten erzeugen

Erster stabiler Projektstand: `v0.1.0`. Aus einem sauberen, geprüften Quellcommit
in einem Build ein lokales `linux/amd64`-Image und dieselben OCI-Bytes privat
exportieren, zum Beispiel mit einem ausdrücklich lokalen Buildx-Builder:

```sh
docker buildx build --builder LOCAL_BUILDER --platform linux/amd64 --target eos-source \
  --label org.opencontainers.image.source=https://github.com/vbeinlich/EOSPVPrognoseHelfer \
  --label org.opencontainers.image.revision=FULL_COMMIT \
  --label org.opencontainers.image.version=v0.1.0 --provenance=false \
  --output type=oci,dest=/PRIVATE/candidate.oci.tar \
  --output type=docker,name=eos-pv-helper:private-candidate \
  --metadata-file /PRIVATE/candidate-metadata.json .
```

Kein `--push`. Metadaten-Digest, OCI-Manifest, Source-Label und exakte Bytes der
enthaltenen `inventory.json` sichern. Smoke am selben lokalen Image:
`python scripts/unraid_smoke.py --image eos-pv-helper:private-candidate --revision FULL_COMMIT`.
Dann bei sauberem, identischem Git-Checkout:

```sh
python scripts/source_bundle.py --image eos-pv-helper:private-candidate \
  --output /PRIVATE/eos-pv-helper-v0.1.0-sources.tar.gz --cache /PRIVATE/source-cache
```

Das Archiv enthält SHA256-indexierte OS-Quellen, passende GCC-SRPMs samt
Distributorpatches, LGPL-/MPL-Python-Quellen, ODbL-Daten/Leser, EOS und eigenen
Quellcode/Buildanleitung. Es bleibt hier privat und außerhalb des Laufzeitimages.
[Lizenzprüfung und genaue Provenienz](LICENSE_REVIEW.md).

Eine Neubuild-, Squash- oder Rebase-Revision benötigt einen neuen Kandidaten und
neue Freigabe; keine Labels nachträglich umschreiben. Transitive Updates können
das Inventar trotz unverändertem Projektcode ändern.

## Verbindliche Release-Gates

1. Vollständige private Doctor-Abnahme gemäß
   [DOCTOR_PRIVATE_ACCEPTANCE.md](DOCTOR_PRIVATE_ACCEPTANCE.md). Aktuell `doctor=null`;
   kein vollständiger Live-Beleg wird behauptet. Historische Exporte ausdrücklich
   als solche prüfen und vom Betreiber bestätigen lassen. Keine weitere
   Produktionsoptimierung auslösen.
2. Lizenzreview des exakten Kandidaten: `license_review` braucht Reviewer,
   Zeitpunkt, Image-Digest, Roh-Inventar-SHA256, Source-Commit, Version,
   Quellmaterial-SHA256 und versionierte öffentliche Quellarchiv-URL.
   `approved=false` bleibt bis zur tatsächlichen Freigabe. Die implementierte
   Quellenzuordnung ist keine fingierte Betreiberfreigabe.
3. Explizite Betreiberfreigabe: `operator_approved=true`, `status=approved`,
   echte Abnahmekommentare und akzeptierter Laufzeit-Commit. Historischer Doctor
   benötigt zusätzlich `historical_snapshot_operator_approved=true`.
   `python scripts/release_gate.py --image-digest SHA256 --source-revision FULL_COMMIT --version v0.1.0`
   muss mit echten Belegen bestehen. Der aktuelle Datensatz sperrt absichtlich.
4. Nach ausdrücklicher Erlaubnis das geprüfte Quellmaterial als anonym abrufbaren
   versionierten GitHub-Release-Asset bereitstellen, bevor erstmals neue öffentliche
   Image-Bytes bereitgestellt werden. Dies ist hier nicht erfolgt. Kein bloßes
   späteres Quellenversprechen. Promotion lädt dieses Archiv anonym und prüft
   äußeren Hash sowie vollständige Übereinstimmung mit dem Image-Inventar.
5. Nach gesonderter Erlaubnis exakt das geprüfte OCI-Archiv initial in die Registry
   übertragen, Digest erhalten, nicht neu bauen. Dafür existiert bewusst kein
   automatischer CI-Upload. Danach anonymer Pull und Offline-Smoke desselben Digests.
6. Vor Aktivierung: `public-image-release` als geschütztes GitHub-Environment mit
   erforderlichem Review einrichten; `main` schützen und Registry-Schreibrechte
   anderer Workflows/Tokens begrenzen. Diese Administration wurde nicht vorgenommen
   oder als vorhanden bestätigt. Erst nach Freigabe `PUBLICATION_ENABLED=true`
   setzen sowie im Record `publication.enabled=true`. Erste `latest`-Zuordnung
   braucht zusätzlich `publication.allow_initial_latest=true`.
7. Source-Commit muss mit grüner Push-CI in `main` enthalten sein; Versionstag
   zeigt genau darauf. `workflow_dispatch` zunächst ohne apply. Erst nach Review
   des Plans `apply=true`. Alle Versionen/Refs teilen einen globalen Concurrency-Lock.
   Unveränderliche Versionstags, wiederholte Registry-Prüfung und SemVer-Vergleich
   verhindern das Zurücksetzen von `latest` durch verspätete ältere Läufe.
   Derselbe Digest/Version ist idempotent; Auth-/Netzfehler sperren.

Registry V2 hat keinen portablen atomaren Compare-and-swap für Tags. Der Schutz
gilt für den einzigen verwalteten Publisher; externe/manuelle Schreiber müssen
per Berechtigungen ausgeschlossen werden. Unerwartete Änderungen führen zum
Abbruch, nicht zum Überschreiben oder Retry.

Erst danach stabilen GitHub-Release mit Digest, Inventar, Quellmaterial, CI- und
Abnahmebelegen veröffentlichen und das XML bewusst auf den geprüften Stand setzen.
Kein Schritt ist durch grüne Unit-Tests automatisch freigegeben.

## Unraid-Update und Rollback erst nach separater Freigabe

Vorher Digest, Startargumente/Mounts und konsistente private Sicherung festhalten.
Konfiguration, Secrets, Cache, `sync-state.json` und `solution-*.json` erhalten;
keine Appdata-Neuinitialisierung oder zweite Instanz mit gleichem Output. Nur den
Helfer aktualisieren, anschließend Modus, Health und Doctor prüfen. Rollback auf
den vorherigen Digest, keine Claims zurücksetzen. Ungewisse oder ausgeführte
Events dürfen nie erneut ausgelöst werden. EOS, evcc, HA und E3/DC bleiben
unverändert. Der bisherige Template-/Produktionsdigest bleibt hier erhalten.

# Helper-Migration und Rollback: nur nach separater Freigabe

Dieses Dokument ist ein vorbereiteter Betreiberplan. Der Auftrag installiert
nichts auf Unraid, ersetzt kein Image und verändert keinen produktiven Zeitplan.
Die technische Reviewbasis ist PR #27, Commit
`3f47313e3f95b16aff55d4499768c4e00422a570`.

## Freigabepunkte vor jeder produktiven Änderung

1. Diesen Draft-PR und PR #27 unabhängig technisch prüfen. CI und
   [PASS/BLOCKED-Bericht](EVIDENCE_WRITER_REVIEW.md) gegen den genauen Head lesen.
   Die bestätigte Abwesenheit der Archive im alten Image ist kein Backfill-Auftrag.
2. Kandidatenquelle einfrieren und neues Helper-Image in einem getrennten,
   freigegebenen Build-/Release-Verfahren prüfen. Dieses PR pusht kein Image.
   Quellen-/Lizenzinventur, Architektur, native Revision, installiertes
   `evidence-writer.json`, Image-ID/OCI-Digest und Git-Head privat dokumentieren.
   Kein bewegliches `latest` und keine Übertragung alter Digest-Freigaben.
3. Auf demselben Dateisystem wie der spätere Archivpfad in einem **neuen privaten
   Testverzeichnis** Non-root-Schreiben, Modus 0700/0400, exklusive Hardlinks,
   Datei-/Verzeichnis-fsync, Neustart und lesenden Worker prüfen. Das reale
   Unraid-User-Share-/FUSE-Verhalten ist lokalem Docker nicht gleichzusetzen.
   Keine Probe in Originaldateien oder existierenden Claims durchführen.
4. Freien Platz und Aufbewahrung privat planen: keine automatische Löschung,
   bis 8 MB je Original und 60 MB ZIP, zusätzlich mindestens 1 MiB Reserve beim
   Commit. Last und NAS-I/O parallel zum normalen EMS sind noch abzunehmen.
5. Aktuelle Command-/Env-/Mount-/UID-/Ressourcen- und Netzwerkparameter privat
   sichern, ebenso TOML und Output konsistent unter Beachtung des Sync-Locks.
   Keine Geheimnisse in öffentliche Reports oder GitHub kopieren.
6. Den bisherigen Digest ausdrücklich als Rollback erhalten:

   `ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`

   Bestehendes Image nicht prunen. Eine offline verfügbare private Sicherung
   und ihre Wiederherstellbarkeit sind Betreiberaufgabe, bevor etwas wechselt.
7. Erst nach dokumentiertem Gegenreview und **ausdrücklicher Betreiberfreigabe**
   ein Wartungsfenster für genau den bestehenden Helper vereinbaren. EOS, evcc,
   Home Assistant, E3/DC und der HTML-User-Scripts-Zeitplan bleiben unberührt.

## Reproduzierbarer lokaler Review

Nur auf dem getrennten Review-Rechner, gegen den eingefrorenen PR-Head:

```sh
docker build --target evidence-candidate \
  --build-arg EOS_REF=8a8cd43a1915668927eda5504b7de039c2e762b4 \
  -t eos-pv-helper:evidence-review .
docker build -f replay-worker/Dockerfile --target runtime \
  -t ems-replay-worker:evidence-review .
python scripts/evidence_writer_container_smoke.py \
  --helper-image eos-pv-helper:evidence-review \
  --worker-image ems-replay-worker:evidence-review \
  --report /PRIVATE/NEW-evidence-writer-pipeline.json
```

Nur lokale Docker-Endpunkte werden akzeptiert. Der Test erzeugt neue zufällig
benannte synthetische Volumes und entfernt ausschließlich diese nach Ende.
Kein produktiver Output, Config-Mount, Docker-Socket oder Gerät gelangt in die
Testcontainer. Der Helper-Kandidat wird ohne Änderung seines Standardbetriebs
über einen geschlossenen Testtransport aufgerufen: ein echter nativer
Vorwärtslauf erzeugt die synthetische Modellantwort; die Suche bleibt gesperrt.
Der getrennte Worker führt genau seine zwei festen nativen Replays aus.

Test mit allen bisherigen Gates:

```sh
docker build -f tests/integration/Dockerfile -t eos-pv-helper:evidence-test .
docker run --rm --network none --read-only --user 10001:10001 --cap-drop=ALL \
  --security-opt=no-new-privileges --tmpfs /tmp:rw,exec,nosuid,nodev,mode=1777 \
  --tmpfs /tmp/eos-test:rw,nosuid,nodev,mode=1777 \
  eos-pv-helper:evidence-test -q -p no:cacheprovider -m 'not genetic_execution'
```

Keine privaten Originale sind für diese Tests erforderlich. Ein später separat
freigegebener privater NAS-Test darf ausschließlich bereits gespeicherte
Originale read-only verwenden und nichts öffentlich hochladen.

## Spätere Aktivierung des bestehenden Helpers

Nach den Freigaben und außerhalb eines laufenden Dispatches den bestehenden
Helper kontrolliert anhalten. Kein erzwungener Abbruch während eines POSTs;
verbleibende `uncertain`-Claims bleiben zur manuellen Prüfung gesperrt. Kein
zweiter Helper darf parallel auf dasselbe Output-Verzeichnis schreiben.

Den geprüften neuen Digest verwenden. Die bisherige reguläre Sync-Kommandozeile,
Freigaben, Env-Werte und Mounts beibehalten; die Beispielkonfiguration ist kein
Ersatz für die private Produktionskonfiguration. Insbesondere startet das
Standard-CMD `run` keinen regulären GENETIC-Sync. `DRY_RUN=true` blockiert wie
bisher sämtliche Schreib-Dispatches. Der neue Writer ändert diese Schalter
nicht. Bestehende produktiv freigegebene Werte nicht aus diesem Dokument ableiten.

Als einzige neue Writer-Freigabe in der gesicherten privaten TOML:

```toml
[evidence]
enabled = true
```

Falls die Tabelle schon existiert, deren Wert ändern statt sie doppelt anzulegen.
Der persistente Original-Output bleibt erhalten. Der Kandidat benötigt dort
unter UID/GID 10001:10001 die bereits vorgesehenen Schreibrechte. Keine pauschalen
rekursiven Rechteänderungen an alten Originalen, Sidecars oder Secrets.

Auf den **nächsten ohnehin regulären** GENETIC-Erfolg warten. Kein manueller
POST, kein Preisversionswechsel zu Testzwecken, kein Claim-Reset und kein
Nachoptimieren. Zu prüfen sind:

- Original-Lösung und Claim weiterhin im bisherigen Format, genau ein regulärer
  Dispatch für diese Version.
- `sync-report.json.evidence.status=archived`, Vertragskennung v2 und ZIP-Hash.
- Finales ZIP Modus 0400, genau sieben vollständige Originalartefakte, valide
  Byte-/Claim-/Request-/Kontextbindung; `ready_for_native_replay` bedeutet noch
  keine native Ergebnisverifikation.
- Eine weitere Sync-Minute derselben Version verändert weder ZIP noch Lösung
  und behält die ursprüngliche Planidentität im aktuellen Report.

Erst danach den Worker gemäß [PR-#27-Betriebsplan](REPLAY_WORKER_UNRAID.md)
separat freigeben. Soll bereits der erste neue Claim automatisch verarbeitet
werden, muss sein Aktivierungswasserzeichen vor diesem regulären Claim liegen.
Andernfalls nur diese ausdrücklich gewählte neue Version manuell mit `--version`
verarbeiten; keine pauschale Freigabe alter Historie. Originale ausschließlich
read-only, privater Katalog außerhalb des Nginx-Bereichs. Den HTML-Refresh nicht
zum Replay-Auslöser machen; sein Minutenplan bleibt gleich.

## Fehlerpfad und Rollback

Ein Archivfehler ist ein eigener Nachweisfehler und ändert weder Solvererfolg
noch Originalclaim. Health wird negativ; Worker/Anzeige bleiben ohne verifizierte
Flüsse. Erst Diagnose, keine automatische Wiederholung oder Reparatur mit neuen
Prognosen. Vollständige `.ready`-Bytes kann der neue Writer nach Neustart prüfen
und publizieren. Ein Fragment oder fehlender Staging-Stand bleibt unbelegt.

Bei unerwartetem Verhalten den getrennten Replay-Worker anhalten. Den Helper
kontrolliert außerhalb eines Dispatches stoppen und den gesicherten alten Digest
mit seiner ursprünglichen privaten Konfiguration, Command-/Env-/Mount-Parametern
wieder einsetzen. Derselbe aktuelle Output bleibt bestehen: keine Rücksetzung
von `sync-state.json`, keine Wiederherstellung eines älteren Claimsnapshots und
keine neue Optimierung als Rollback-Test.

Das State-/Lösungsformat und die Versionsbildung wurden nicht migriert. Der alte
Helper ignoriert neue ZIPs und zusätzliche Reportmetadaten; er erzeugt selbst
keine Evidenzarchive. Neue Archive, Ready-Dateien, Claims, Sidecars und Katalog
bleiben privat erhalten und werden nicht gelöscht oder umgeschrieben. Den
zuletzt gültigen HTML-Stand beibehalten. Originale/Geheimnisse gelangen weder
zum Nginx noch ins Repository. Anschließend ist der Produktivzustand wieder
`BLOCKED` für neue automatische Replay-Nachweise; die historischen Angaben
werden dadurch nicht neu bewertet.

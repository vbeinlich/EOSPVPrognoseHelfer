# EMS v1.1: vorbereitetes privates Unraid-Testpaket

Helper und Worker stammen ausschließlich aus Git-Commit
`546baa63ade70cab20c67a7410575c8d2b8dc667` (PR #28, Basis PR #27).
Linux/amd64, native EOS-Revision `8a8cd43a1915668927eda5504b7de039c2e762b4`.
Die Installationswerkzeuge sind eine getrennte Ergänzung; der EMS-Quellcode
wurde dafür nicht verändert. Kein Registry-Push, Release oder Zugriff auf Unraid.

## Enthalten

- Zwei eindeutig benannte Docker-TARs, SHA256 in `manifest.json` und `SHA256SUMS`.
- Vollständiges Git-Quellarchiv, installierte Modul-/Bibliotheksinventare und
  mitgelieferte Lizenznachweise unter `reports/` und `licenses/`.
- Manuelles Installations-/Rollback-Skript, Offline-Archivprüfung, isolierter
  Worker-Start und geprüfter Publisher-Befehl. Keine Änderung am Minutenplan.

`manifest.json` unterscheidet den Docker-Config-/Image-ID, die lokale
Containerd-/Manifest-ID und die TAR-Prüfsumme. Ein Registry-Digest existiert
für diese nur lokal gebauten Images nicht: `registry_manifest_digest=null`.
Docker Desktop meldet bei `image inspect .Id` teilweise die Manifest-ID,
klassisches Docker auf Unraid die Config-ID. Das Skript berücksichtigt beide.

## Auf Unraid: ausschließlich manuell

Das Paket zuerst privat nach
`/mnt/user/appdata/ems-dashboard-review/` übertragen. Codex überträgt nichts.
Die äußere Paketprüfsumme aus dem Abschlussbericht vergleichen und dann:

```sh
cd /mnt/user/appdata/ems-dashboard-review
tar -xf ems-v11-test-546baa63-20261105.tar
cd ems-v11-test-546baa63-20261105
sha256sum -c SHA256SUMS
bash tools/unraid-test.sh install
```

Das Skript erwartet genau den bestätigten laufenden `eos-pv-helper`, dessen
Image-ID `sha256:e1c47a73e80272fd4fae9653d02ff9b993e894b4e6d39495e49b6fbd93f3495d`,
UID/GID `10001:10001`, read-only Root, Restart `no` und unverändertes Kommando:
`sync --config /app/config.toml --refresh-source --write-eos`.
Unerwartete Konfigurationen werden vor dem Austausch abgelehnt.

Vorher prüft es die SHA256 der bereits vorhandenen Betreiber-Rollback-TAR und
sichert den tatsächlichen Container-Inspect, TOML, aktive Secret-Dateien,
benötigte Datei-Eingaben und weitere eingebundene Konfigurationsdateien privat.
Masterbackup/Plan bleiben root-eigen mit 0700/0600. Environment-Werte stehen
im privaten Inspect, nicht in der Terminalausgabe. Fehlende Pflichtdateien
brechen den Vorgang ab. Der Host benötigt Bash, Docker, curl, flock und coreutils;
Python wird aus dem bestehenden Helper genutzt, nicht auf Unraid installiert.

Danach wird das Helper-TAR geladen. Der Wechsel wartet auf den freien bestehenden
Sync-Lock, sendet dort TERM und wartet auf das reguläre Ende. Kein zeitgesteuertes
SIGKILL eines laufenden Dispatches. Nur `[evidence] enabled = true` wird in der
gesicherten TOML geändert; die übrige TOML wird semantisch auf Gleichheit geprüft.
Der alte Container bleibt gestoppt unter `eos-pv-helper-before-<UTC>` erhalten.
Mounts, Environment, Kommando, Limits und Freigaben werden aus dem tatsächlichen
Inspect übernommen und nach Start geprüft. Der neue Image-ID wird schon VOR
dem Start kontrolliert. Es wird kein manueller Optimierungs-POST ausgelöst.

Die Ausgabe nennt den privaten Backup-Pfad und den exakten Rollback-Befehl.
Diesen Pfad im Folgenden als `BACKUP` verwenden:

```sh
BACKUP='/mnt/user/appdata/ems-dashboard-review/backup/ems-v11-DATUMTZEITZ'
# Erst nach dem nächsten OHNEHIN regulären GENETIC-Erfolg:
bash tools/unraid-test.sh check-archive "$BACKUP"
```

Der Archivtest ist vollständig offline und prüft neue, nach dieser Installation
entstandene Erfolgsclaims, sieben Originalartefakte plus Manifest, Modi, Bytehashes,
Request-/Modellbindung und `ready_for_native_replay`. Er funktioniert auch, wenn
der aktuelle Sync-Report später wieder `waiting-publication` zeigt. Alte Lösungen
ohne ursprüngliches finales ZIP werden nicht vervollständigt. Health kann bis
zum ersten neuen belegten Lauf wegen älterer fehlender Evidenz negativ sein;
ein laufender Prozess allein gilt nicht als Archivabnahme.

## Worker erst nach bestandenem Archivtest

Den BISHER tatsächlich verwendeten privaten `--replays`-Sidecar-Pfad übernehmen,
damit die verifizierten Flüsse vom 29./31.10. erhalten bleiben. `none` ist nur
für eine Installation ohne bisherige Sidecars vorgesehen.

```sh
bash tools/unraid-test.sh start-worker "$BACKUP" '/PFAD/ZUM/BISHERIGEN-SIDECAR.json'
bash tools/unraid-test.sh publisher-test "$BACKUP"
bash tools/unraid-test.sh publisher-command "$BACKUP"
```

Der Worker bekommt keine Konfiguration, Secrets, Geräte, Netzwerkverbindung oder
Docker-Socket. Originale nur read-only, eigenes privates 0700-Arbeitsverzeichnis
`/mnt/user/appdata/ems-dashboard-review/replays-v11-546baa63`, 0,5 CPU, 768 MiB,
128 PIDs, geringe Priorität, native Timeouts und globaler Einprozess-Lock.
Bestehende Sidecars werden geprüft importiert; historische Claims bleiben gleich.
Das Aktivierungswasserzeichen wird bei erstmaliger Anlage auf den echten
Helper-Installationszeitpunkt gesetzt. Auch neue Archive aus der Zwischenzeit
gehen damit nicht verloren. Bestehender Worker-State wird nicht zurückgesetzt.

Nach erfolgreichem Test nur die vom letzten Befehl ausgegebene Publisher-Zeile
im vorhandenen User-Script ersetzen. `* * * * *`, Browser-Reload, Nginx und dessen
Mounts bleiben unverändert. Die Werkzeuge im Paket benutzen den unveränderten
Publisher und den konsistenten Katalog-Snapshot-Adapter aus PR #27.
Die bisherige Publisher-Zeile vorher privat notieren; das Skript editiert keine
User-Scripts-Dateien und keinen Zeitplan.

Kurzer Funktionstest: `worker-accepted.json` im privaten Backup meldet
`native_flows_verified=true`; danach Dashboard `http://192.168.0.186:8505` neu laden.
Der native Replay ändert keine Originale. Ein Neustart berechnet einen verifizierten
Originalhash nicht erneut. Fehlende/abweichende Nachweise bleiben „Nicht belegt“.
Testcontainer haben Restart `no`; nach einem NAS-Neustart sind Testhelper und
Worker deshalb bewusst manuell zu starten, solange kein Autostart freigegeben ist.

## Rollback

```sh
bash tools/unraid-test.sh rollback "$BACKUP"
```

Stoppt den zu diesem Paket gehörenden Worker, beendet den neuen Helper kontrolliert,
stellt ausschließlich die ursprüngliche TOML wieder her und startet den erhaltenen
alten Container unter seinem ursprünglichen Namen. Claims, Lösungen, Quellen-Caches,
Archive und Sidecars werden NICHT zurückgesetzt, gelöscht oder umgeschrieben.
Spätere Betreiberänderungen an der TOML werden nicht ungeprüft überschrieben.
Bei Fehlern während des Wechsels versucht das Skript denselben kontrollierten
Rollback automatisch; ein nicht sicher beendbarer Container wird niemals gewaltsam
gestoppt oder durch einen zweiten parallel laufenden Helper ergänzt.

Falls die Publisher-Zeile bereits manuell ersetzt wurde, deren gesicherte vorige
Zeile wieder einsetzen; den Minutenplan beibehalten. Unraid-XML-Vorlagen bleiben
unverändert. Ein späteres „Apply/Update“ über die alte GUI-Vorlage kann deshalb
wieder das alte Image einsetzen und gehört nicht zu diesem Testwechsel.

Die Betreiberbestätigungen zu FUSE, fsync und Rollback-TAR sind keine von Codex
ausgeführte NAS-Abnahme. Tatsächliche Wiederherstellbarkeit der vorhandenen TAR,
private Last-/Dateisystemprüfung und unabhängiger Gegenreview bleiben offen.
Produktive Freigabe folgt nicht automatisch aus CI oder einem erfolgreichen Test.

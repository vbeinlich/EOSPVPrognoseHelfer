# EMS Dashboard v1.0: privater LAN-Betrieb auf Unraid

Vorbereitung auf Basis von PR #25 / `8011a6d2849f5f17479dd1293f5806d39b3456e7`.
Ziel nach **separater Betreiberfreigabe**: `http://192.168.0.186:8505`.
Diese Anleitung und die CI aktivieren weder Unraid-Webserver noch Scheduler.

## Betriebsstufen und Datengrenzen

**Stufe A:** Der unveränderte, hashgeprüfte Reader aus PR #25 liest archivierte
GENETIC-Pläne, Inspector/Doctor-Nachweise und vorhandene Modellwerte. Er zeigt
SoC am Intervallanfang, Preise, PV, Last und Historie. Erfolgsstatus und
Modellvorteil brauchen die bestehenden Nachweise. Ein einzelnes Lösungs-JSON
belegt keinen erfolgreichen historischen Claim. Ohne passenden Sidecar bleiben
Batterieflüsse, Fenster und Vollzyklen ausdrücklich „Nicht belegt“.

**Stufe B:** Ein separat geprüfter nativer Offline-Replay ergänzt Modellflüsse.
PV grün, Netz blau, Entladung orange, SoC violett. Die Energien sind interne
Speicherenergien; DC-Ein-/Ausgangswerte stehen zusätzlich im Sidecar. Vollzyklen
sind interne Entnahme / nutzbare interne Kapazität. Freigaben sind keine Energie.
Alle Werte heißen nachträglich berechnete Modellflüsse, keine damaligen Messwerte.
Der Reader validiert den Sidecar gegen die unveränderten Lösungsbytes,
Parameter, EOS-Quellfingerprints, Replay-Gleichheit und Energiebilanzen.
Er erweitert ihn niemals selbst. Die bestehenden UTC-Regeln gegen doppelte
Zählung überlappender Horizonte bleiben unverändert.

Der 30.10. und neue Pläne ohne passenden Nachweis bleiben offen. Der Sidecar für
29./31.10. erzeugt keinen Nachweis für andere Tage. Null Netzladung in einem
geprüften Modell ist ein gültiges Ergebnis; ein blauer Balken wird nicht erfunden.

## Hash-Abweichung und nachvollziehbare Eingaben

Die bisherigen privaten Sidecars waren an gespeicherte GET-Antworten gebunden.
Der produktive Archivwriter verwendet `json.dumps(data, indent=2, allow_nan=False)`
mit abschließendem LF (`storage.atomic_json`). Das verändert die Bytes gegenüber
der kompakten GET-Antwort, ohne JSON-Werte zu ändern.

| Tag | bisherige GET-Bytes: SHA-256 | Archivformat: SHA-256, identisch mit Betreiberangabe |
| --- | --- | --- |
| 29.10. | `9d2acc2ca585f915784cbd891100fc551cab8b194b2b065a01e0bff1ba5fe284` | `2718a5ad255f12899f130205abba9c84e812f95e90a4b94de1ff34e2e9815beb` |
| 31.10. | `a0cfa244f08b63718a32afad2659fb9fe7a3926b129de6700526b909047d7b84` | `c520f800ed5b043772d47334989f95d6681fe59800f27df0f911f7d95b3f036a` |

Der direkte SMB-Inhaltsabruf scheiterte beim Review mit „Zugriff verweigert“,
auch außerhalb der Sandbox. Es wurden keine NAS-Berechtigungen verändert.
Statt eines angeblichen Downloads wurden neue private Eingabekopien aus den
gespeicherten Antworten im unveränderten Writerformat hergestellt. Ihre **vollständigen
Bytehashes** treffen beide unabhängig vom Betreiber genannten Archivhashes exakt.
Die Dateien sind 121692 bzw. 121786 Bytes groß. JSON-Struktur, Parameter und
Ergebnisse sind unverändert; ein semantischer Ähnlichkeitsvergleich allein wäre
keine Freigabe. Die Herkunft „hashgeprüfte Rekonstruktion, kein SMB-Download“
steht im privaten Erwerbsprotokoll und bleibt im Review ausdrücklich sichtbar.
Ein zusätzlicher direkter Originaltransfer ist für den Gegenreview weiterhin offen.

Reproduzierbares Diagnosewerkzeug **nur am privaten Review-Rechner**:

```bash
python scripts/dashboard_archive_hash_probe.py \
  --saved-response /PRIVATE/saved-get-29.json \
  --expected-sha256 2718a5ad255f12899f130205abba9c84e812f95e90a4b94de1ff34e2e9815beb \
  --write-new /PRIVATE/NEW-solution-29.json
python scripts/dashboard_archive_hash_probe.py \
  --saved-response /PRIVATE/saved-get-31.json \
  --expected-sha256 c520f800ed5b043772d47334989f95d6681fe59800f27df0f911f7d95b3f036a \
  --write-new /PRIVATE/NEW-solution-31.json
```

Das Werkzeug schreibt nur bei exaktem vorgegebenem Bytehash und ausschließlich
eine neue Datei. Es bearbeitet weder Originale noch Sidecars. Bei abweichendem
Hash abbrechen und auf tatsächliche Originale warten; niemals Sidecar-Hashes ersetzen.

Der neue native Replay wurde ausschließlich mit diesen hashgeprüften Archivbytes
ausgeführt: kein Suchlauf, keine neuen Forecasts, keine Baseline. Zwei feste native
Vorwärtsläufe pro Lösung prüfen die lesende Herkunftserfassung. Alle Flüsse und
Prüfresultate stimmen mit dem bisherigen Replay überein; die neue Bindung entsteht
aus den Eingabebytes durch den Exporter. Native EOS-Revision:
`8a8cd43a1915668927eda5504b7de039c2e762b4`.

Neuer **privater** Sidecar: `ems-replay-unraid-hashverified-2026-10-29_31-v2.json`.
Datei-SHA-256: `6b84c9efa446284ae4d90caa3745b70d037d55d142e4eafe910412295c7ecf5d`.
Die alten Sidecars und historischen Dateien bleiben unverändert.

## Paket am Review-Rechner bauen

Python 3.11+, installierte Projektquellen und ein neuer Zielordner in einem
privaten Übertragungsverzeichnis; keine Dateien daraus ins öffentliche Repository:

```bash
python scripts/check_dashboard_hashes.py
python scripts/check_dashboard_lan_hashes.py
python scripts/build_dashboard_lan_package.py \
  --destination /PRIVATE/TRANSFER/NEW-dashboard-lan-v1 \
  --review-commit REVIEWED_40_CHARACTER_COMMIT \
  --private-replays /PRIVATE/ems-replay-unraid-hashverified-2026-10-29_31-v2.json
```

Ohne `--private-replays` entsteht ein reines Stufe-A-Paket. Der Builder rechnet
keinen Replay. `PACKAGE_HASHES.json` enthält alle übertragenen Dateihashes,
Review-Commit und bei Stufe B die Quellhashes. Alle Ziele müssen neu sein.
Der Reader bleibt bytegleich zu PR #25:

- `ems-dashboard-final.pyz`: `ec2666b596700595c34a1aeef058dda1edb0db713e0811451435c87038b2846c`
- `unraid-ems-dashboard.sh`: `312a9f748cf5e928eb665769b057ddfdb64005ce91707b16ad1ef8a13782f04e`

## Verzeichnis- und Rechtekonzept nach Freigabe

```text
/mnt/user/appdata/ems-dashboard-review/
  tools/       # private Reader, geprüfte Hostskripte; nicht im Webserver
  private/     # privater letzter gültiger Export und Locks; nicht im Webserver
  replays/     # nur privater geprüfter Sidecar; nicht im Webserver
  server/      # eigener nginx.conf + optional Compose-Datei
  publish/     # ausschließlich index.html (0644), Verzeichnis 0755
```

Den vorhandenen Output `/mnt/user/appdata/eos-pv-helper/output` und dessen Rechte
nicht ändern. Keine rekursiven `chmod`/`chown` auf appdata, tools oder output.
Der HTML-Reader läuft kurz per `python -I -S -B` im vorhandenen Image unter dessen
Benutzer 10001; Code kommt geprüft über stdin, keine Helferinstallation. Er startet
keine zweite Helferinstanz. Nginx läuft separat als 101:101 und bekommt **nur**
`publish/` und seinen eigenen `nginx.conf` read-only. Das Verzeichnis wird
eingebunden, nicht die einzelne HTML-Datei: atomarer Austausch muss sichtbar bleiben.

Übertragung und Vorbereitung führen ausschließlich Betreiber nach Freigabe aus.
Neue Paketdateien einzeln anhand `PACKAGE_HASHES.json` prüfen. Bereits vorhandene
Reader erneut gegen obige Hashes prüfen; nur bytegleiche Dateien weiterverwenden.
Neue Skripte/Configs ohne CRLF/BOM übertragen. Beispiel für neue Verzeichnisse:

```bash
dashboard_root=/mnt/user/appdata/ems-dashboard-review
test -d "$dashboard_root/tools"
test -d "$dashboard_root/private"
test ! -e "$dashboard_root/publish"
test ! -e "$dashboard_root/server"
test ! -e "$dashboard_root/replays"
install -d -m 0755 "$dashboard_root/publish"
install -d -m 0700 "$dashboard_root/server" "$dashboard_root/replays"
# Prüfte Paketdateien gezielt installieren, SOURCE durch privaten Transferpfad ersetzen:
install -m 0700 SOURCE/tools/unraid-dashboard-publish.sh "$dashboard_root/tools/"
install -m 0700 SOURCE/tools/unraid-dashboard-preflight.sh "$dashboard_root/tools/"
install -m 0644 SOURCE/server/nginx.conf "$dashboard_root/server/"
install -m 0600 SOURCE/server/compose.yaml "$dashboard_root/server/"
install -m 0600 SOURCE/server/user-script.sh "$dashboard_root/server/"
# Optional Stufe B: nur den NEUEN Sidecar kopieren, alten Sidecar nicht ersetzen.
install -m 0600 SOURCE/replays/ems-replay-unraid-hashverified-2026-10-29_31-v2.json "$dashboard_root/replays/"
```

Bei bereits existierenden neuen Zielverzeichnissen erst deren Inhalt prüfen und
die Vorbereitung passend fortsetzen; nicht blind Rechte ändern oder Dateien ersetzen.
`server/` braucht keine allgemeinen Host-Leserechte: Docker bindet die explizite
Datei ein, deren Modus 0644 ist. Private Verzeichnisse werden nicht eingebunden.

Einmaligen Stufe-A-Export zunächst **ohne** Webserver durchführen:

```bash
timeout 70s bash "$dashboard_root/tools/unraid-dashboard-publish.sh" \
  "$dashboard_root/tools" "$dashboard_root/private" "$dashboard_root/publish"
test -s "$dashboard_root/publish/index.html"
```

Stufe B erst nach erneutem `sha256sum` der beiden tatsächlichen Originale und
des neuen Sidecars aktivieren. Nur diese private optionale Datei hinzufügen:

```bash
sha256sum "$dashboard_root/replays/ems-replay-unraid-hashverified-2026-10-29_31-v2.json"
timeout 70s bash "$dashboard_root/tools/unraid-dashboard-publish.sh" \
  "$dashboard_root/tools" "$dashboard_root/private" "$dashboard_root/publish" \
  --replays "$dashboard_root/replays/ems-replay-unraid-hashverified-2026-10-29_31-v2.json"
```

Exitcode 0 = gültiger Export; 2 = Eingabe-/Nachweisfehler, bisherige Plandaten mit
Fehlerhinweis; 1 = Transport-/Codefehler. Keine Aktualisierungsfreigabe aus einem
Exitcode 2 ableiten. Daten und Darstellung des letzten gültigen HTML bleiben erhalten.
Ein Initialfehler kann nur eine Fehleransicht ohne erfolgreiche Pläne erzeugen.

## Port und Adresse unmittelbar vor Start prüfen

```bash
bash "$dashboard_root/tools/unraid-dashboard-preflight.sh" 192.168.0.186
docker version --format '{{.Server.Version}}'
docker inspect eos-pv-helper --format '{{.Config.Image}} {{.Config.User}}'
```

Der Preflight liest nur `ip`, `ss`, Docker-Container und PortBindings. Er lehnt
falsche/öffentliche Adressen, jeden TCP-Listener auf 8505 einschließlich IPv6
und bestehende Docker-Portbindungen ab. Er startet oder beendet nichts. Ein
anschließender konkurrierender Portstart bleibt möglich: Docker muss beim Start
ebenfalls erfolgreich binden. Auf Unraid wurde dieser Preflight noch nicht ausgeführt.

## Eigener Nginx: zwei alternative Installationswege

Image fest gepinnt:
`nginxinc/nginx-unprivileged@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03`.
Im lokalen Test Nginx 1.30.6, UID/GID 101. Read-only Root, alle Capabilities
entfernt, no-new-privileges, nur /tmp als begrenztes tmpfs, PID-/RAM-/CPU-Limit.
Es gibt keine externen Assets, API, CGI, Proxyziele, TLS- oder DNS-Abrufe im Dashboard.
Nginx liefert nur `/` und `/index.html`; `/favicon.ico` antwortet leer mit 204,
alle anderen Pfade 404; nur GET/HEAD sind erlaubt. Auch versehentlich im
Publikationsordner abgelegte JSON-Dateien sind über HTTP nicht abrufbar.

Das separate Bridge-Netz deaktiviert Container-Peer-Kommunikation. Es ist **keine
Egress-Firewall**; ausgehende Konnektivität wird nicht als gesperrt behauptet.
`internal: true` wurde lokal verworfen, weil damit der veröffentlichte Host-Port
nicht erreichbar war. Kein Host-Netzwerk, keine Änderung von Docker-Daemon oder
Host-Firewall. Keine weiteren Container an dieses Netz anschließen.

**A: Compose, falls auf Unraid vorhanden.** Vor `up` nochmals Preflight ausführen.

```bash
export DASHBOARD_ROOT=/mnt/user/appdata/ems-dashboard-review
export DASHBOARD_LAN_IP=192.168.0.186
export DASHBOARD_PORT=8505
docker compose -f "$dashboard_root/server/compose.yaml" config
docker compose -f "$dashboard_root/server/compose.yaml" pull
bash "$dashboard_root/tools/unraid-dashboard-preflight.sh" "$DASHBOARD_LAN_IP"
docker compose -f "$dashboard_root/server/compose.yaml" up -d --pull never
docker compose -f "$dashboard_root/server/compose.yaml" ps
```

**B: Docker CLI ohne Compose.** Nur einen der beiden Wege verwenden.
Vorab muss der Name `ems-dashboard-lan` ebenso wie das Netz
`ems-dashboard-lan-static` unbenutzt sein; bei Konflikten abbrechen.

```bash
docker container ls -a --filter name=ems-dashboard-lan
docker network ls --filter name=ems-dashboard-lan-static
docker pull nginxinc/nginx-unprivileged@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03
bash "$dashboard_root/tools/unraid-dashboard-preflight.sh" 192.168.0.186
docker network create --driver bridge \
  -o com.docker.network.bridge.enable_icc=false ems-dashboard-lan-static
docker run -d --name ems-dashboard-lan --restart unless-stopped \
  --user 101:101 --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --pids-limit 32 --memory 64m --cpus 0.25 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --network ems-dashboard-lan-static --publish 192.168.0.186:8505:8080 \
  --mount "type=bind,src=$dashboard_root/publish,dst=/srv/dashboard,readonly" \
  --mount "type=bind,src=$dashboard_root/server/nginx.conf,dst=/etc/nginx/nginx.conf,readonly" \
  --log-driver json-file --log-opt max-size=1m --log-opt max-file=2 \
  --health-cmd 'wget -q -O /dev/null http://127.0.0.1:8080/index.html' \
  --health-interval 30s --health-timeout 3s --health-retries 3 --health-start-period 5s \
  --entrypoint nginx \
  nginxinc/nginx-unprivileged@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03 \
  -c /etc/nginx/nginx.conf -g 'daemon off;'
```

Keine Router-Portfreigabe, kein öffentlicher Proxy, kein Zugriff aus dem Internet.
Die interne IPv4-Bindung ist im Inspect nachzuweisen. Bindung an eine LAN-Adresse
ersetzt keine korrekte Router-Konfiguration; deren Änderung ist nicht Teil dieses Pakets.
Nginx erhält niemals `/output`, Sidecars, Tokens, EMS-Konfiguration, Geräte oder Socket.

## Privater erster Sichttest nach Betreiberfreigabe

1. Einmaliger Export, dann Webserver, zunächst **kein Scheduler**.
2. `curl -fsS -D - http://192.168.0.186:8505/ -o /dev/null` auf Unraid;
   Status 200, `Cache-Control: no-store`, keine Weiterleitung zu EOS.
3. Windows-Browser und Smartphone **im Heimnetz**: dieselbe URL öffnen.
   Dark Mode, vollständige breite/schmale Ansicht und 24 h / 7 / 30 Tage prüfen.
4. Alle regulär erfolgreich archivierten Pläne einschließlich der bisher gemeldeten
   sieben Pläne auswählen. 29./31.10. mit passendem Replay: grün/orange,
   gegebenenfalls blau **nur bei belegter Netzladung**, korrekte SoC-Zeiten,
   interne Fenster/Zyklen und Modellhinweis. Neuere Pläne ohne Replay: „Nicht belegt“.
5. Entwicklertools: nur Dashboard-HTML und ggf. leeres favicon, keine Fremdrequests.
   `curl -i http://192.168.0.186:8505/replays/test.json` muss 404 ergeben;
   `curl -i -X POST http://192.168.0.186:8505/` muss 405 ergeben.
6. Mit `docker inspect` zwei read-only Dateibindungen, UID 101, Host-IP 192.168.0.186,
   CapDrop ALL, ReadonlyRootfs, no-new-privileges und Healthcheck kontrollieren.
7. Regulären nächsten Dry-Run abwarten, keinen Suchlauf auslösen. Einmaligen
   HTML-Leseexport erneut ausführen; neuer Plan muss nach spätestens 60 s Browser-
   Reload sichtbar werden. Erfolg/Claims und Nachweise getrennt kontrollieren.

Echte Originale für Fehlertests niemals beschädigen. Fehlererhalt ist lokal mit
synthetischen Archivkopien, defektem Transport, falschen Codehashes und korrupten
Eingaben geprüft. Auf Unraid nur lesend prüfen; keine Teständerungen an `/output`.

## Automatischer Serverexport: gesonderte Schedulerfreigabe

Der vorhandene Helfer braucht keine Änderung. Ein belegter neuer Archivplan ist
beim nächsten Readerlauf sichtbar. Ein direkter Prozesshook würde den produktiven
Helfer ändern; deshalb ist eine getrennte, kurze User-Scripts-Abfrage vorbereitet.
Nach einmal erfolgreichem Sichttest und **gesonderter Freigabe** das mitgelieferte
`server/user-script.sh` als eigenes Unraid User Script übernehmen. Optional nur
den bereits geprüften Sidecarpfad ergänzen. Zeitplan: jede Minute (`* * * * *`).
Jetzt weder installieren noch aktivieren.

Der Zeitplan ruft ausschließlich den HTML-Leseexport auf, kein EOS-POST, Replay
oder Optimierungsprogramm. `timeout 70s` begrenzt den Hostjob, der Readertransport
ist zusätzlich auf 45 s begrenzt. Nicht blockierende Locks verhindern parallele
Exporte; der Archivreader beachtet die bestehenden Sync-Locks. Atomarer Rename im
Publikationsverzeichnis erhält vollständige HTML-Dateien. Bei Fehlern bleiben die
letzten Plandaten mit Aktualisierungswarnung erhalten; bei Fehlern schon vor sicherer
Pfadvalidierung wird nichts geschrieben und die bestehende Stale-Warnung erscheint
spätestens nach drei Minuten. Browser-Reload alle 60 s ersetzt diesen Export nicht.

Zum Zurücknehmen nur den neu angelegten User-Scripts-Zeitplan deaktivieren und den
eigenen Nginx-Container stoppen (`docker stop ems-dashboard-lan` für den CLI-Weg,
Compose `stop` für den Compose-Weg). Helfer/EOS, Ports 8503/8504 und Originaldaten
bleiben unberührt. Keine pauschalen Container-/Netzwerk-Aufräumbefehle verwenden.

## Spätere Replay-Automation: Entwurf, nicht aktiviert

Ein separater Review-Worker dürfte neue **stabile und vollständig archivierte**
Originalbytes anhand eines append-only Hashregisters übernehmen. Nur vorhandene
Parameter/Freigaben, feste gepinnte EOS-Revision und isolierter temporärer Zustand;
`--network none`, nicht root, read-only Eingaben, kein Docker-Socket und keine
produktive Konfiguration. Für jede Datei zwei feste native Replays mit allen
Gleichheits-/Herkunfts-/Bilanzprüfungen. Kein Suchlauf/Forecast/Baseline-Fallback.
Bytehash vor/nach Export unverändert, neue exklusive versionierte Sidecars und
separate Prüffreigabe. Fehlgeschlagene Pläne in Quarantäne, keine Flussbehauptung.

Erst ein gesondert freigegebener Übertragungsprozess dürfte einen validierten
Katalogpfad für den Reader bereitstellen. Der Reader validiert jeden Match erneut;
unbekannte Hashes bleiben unbekannt. Die aktuellen Tests prüfen dieses Prinzip
einschließlich falscher Quellhashes, Provenienz, Bilanzen und neuer synthetischer
Archiv-Ereignisse. Kein permanenter Replay-Worker, automatischer Transfer oder
Replay-Scheduler gehört zur jetzigen Installation.

## Referenzen der Infrastruktur

- [NGINX Unprivileged: Nutzer, Port und temporäre Pfade](https://github.com/nginx/docker-nginx-unprivileged)
- [Docker: explizite Host-IP bei Portveröffentlichung](https://docs.docker.com/engine/network/port-publishing/)
- [Nginx: location, try_files, disable_symlinks und Dateicache](https://nginx.org/en/docs/http/ngx_http_core_module.html)

Der lokale Test belegt die konkrete gepinnte Konfiguration. Tatsächliche NAS-
Netzerreichbarkeit, Smartphone und die Gesamtheit der sieben Originalarchive bleiben
Gegenstand der privaten Betreiberabnahme, siehe `DASHBOARD_LAN_REVIEW.md`.

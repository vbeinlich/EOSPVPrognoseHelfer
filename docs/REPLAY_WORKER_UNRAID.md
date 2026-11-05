# EMS-Dashboard v1.1: separater nativer Offline-Replay

Ausgangspunkt ist PR #26 / `f9362f53932594fa37800f1939405d47c9a6365f`.
Dashboard v1.0 und der minuetliche User-Scripts-Zeitplan laufen bereits auf
Unraid. Dieser PR installiert, startet oder aendert dort nichts. Die folgenden
Befehle sind ein privater Inbetriebnahmeplan nach Gegenreview und Betreiberfreigabe.

## Daten- und Sicherheitsgrenze

Der Worker bekommt nur den unveraenderten Output als `/archive:ro` und ein neues
privates Arbeitsverzeichnis als `/replays:rw`. Keine produktive Konfiguration,
Tokens, Env-Dateien, Geraete, Netzwerkverbindungen oder Docker-Sockets werden
in den Container gegeben. Das Host-Startskript benutzt den lokalen Docker-Daemon;
dieser Zugriff wird nicht in den Worker weitergereicht. Der Nginx-Container
behaelt ausschliesslich seinen bisherigen read-only Zugriff auf `publish/`.

Native Referenz: `8a8cd43a1915668927eda5504b7de039c2e762b4`, kompletter
Quellarchivhash im eigenen Dockerfile, zusaetzlich die unveraenderten nativen
Dateifingerprints. Der numerische Stack ist auf NumPy 2.4.6, SciPy 1.17.1 und
Pydantic 2.14.1 begrenzt; die vollstaendige Abhaengigkeits-/Quelleninventur bleibt
im Image. Kein neues Helper-Image und kein EOS-Deployment.

## Vorab am getrennten Review-Rechner

```bash
git checkout REVIEWED_WORKER_COMMIT
python scripts/check_dashboard_hashes.py
python scripts/check_dashboard_lan_hashes.py
python scripts/check_replay_worker_hashes.py
docker build -f replay-worker/Dockerfile --target runtime -t ems-replay-worker:reviewed .
docker build -f replay-worker/Dockerfile --target test -t ems-replay-worker:review-test .
docker run --rm --network none --read-only --user 10001:10001 --cap-drop=ALL \
  --security-opt=no-new-privileges --cpus=1 --memory=768m --memory-swap=768m \
  --pids-limit=128 --tmpfs /tmp:rw,exec,nosuid,nodev,size=256m,mode=1777 \
  ems-replay-worker:review-test
python scripts/replay_worker_container_smoke.py \
  --image ems-replay-worker:reviewed --fixture-image ems-replay-worker:review-test
```

Nur Tests mit synthetischen ausfuehrbaren Docker-Mocks brauchen `exec` auf ihrem
eigenen `/tmp`. Der tatsaechliche Worker verwendet stets `noexec`. Der Smoke-Test
legt ausschliesslich zufaellig benannte lokale Testvolumes/-container an und
entfernt nur diese wieder. Er verweigert entfernte Docker-Endpunkte.

Image-ID erfassen und Image **privat** transferieren; dieser PR publiziert kein Image:

```bash
docker image inspect ems-replay-worker:reviewed --format '{{.Id}}'
docker save ems-replay-worker:reviewed -o NEW-private-replay-worker.tar
sha256sum NEW-private-replay-worker.tar
```

Privaten Transfer und Image-ID auf Unraid nach Freigabe unabhaengig pruefen.
Quell-/Lizenzinventur unter `/usr/share/eos-pv-helper/licenses` erhalten. Keine
echten Originale, Replays, Rohparameter oder privaten Screenshots ins Repository/CI.

## Private Vorbereitung nach Freigabe

Ein **neues** Arbeitsverzeichnis unter
`/mnt/user/appdata/ems-dashboard-review/replays-v11` vorsehen; bestehende
`replays/` und historische Sidecars unveraendert erhalten. Beispiel, nur wenn neu:

```bash
root=/mnt/user/appdata/ems-dashboard-review
test ! -e "$root/replays-v11"
install -d -o 10001 -g 10001 -m 0700 "$root/replays-v11"
# Geprueftes neues Hostskript einzeln nach tools/ uebertragen; keine rekursiven Rechteaenderungen.
```

Der Benutzer 10001 muss die bereits vorhandenen Originale und `sync.lock` lesen
koennen. Vorhandene Originalrechte nicht umstellen. Bei fehlendem Zugriff abbrechen
und den Betreiber entscheiden lassen. Die erfolgreiche v2-Archivierung muss beim
regulaeren Helper bereits eingerichtet sein; der Worker aktiviert sie nicht.
Fehlen finale Archive mit kompletter Request-/Solver-Bindung, bleibt Automatik
BLOCKED. Neue Prognosen oder eine zusaetzliche Optimierung sind keine Loesung.

Der lokale, ausschliesslich lesende Test des angegebenen unveraenderten Images
`sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7`
ergab: `evidence`, `historical` und `doctor` sind dort nicht installiert. Eine
zusaetzliche bestehende Archivquelle muss daher privat nachgewiesen werden.
Dieser Befund ist kein Anlass, das produktive Image oder dessen Konfiguration
ohne gesonderte Freigabe zu ersetzen. Der Sidecar-Reader selbst funktioniert
weiter mit dem bestehenden Standalone-Bundle im alten Image.

Der erste Aufruf persistiert einen Aktivierungszeitpunkt. Automatisch werden nur
Claims ab diesem Zeitpunkt beruecksichtigt. Ein spaeter gestarteter regulaerer
Dry-Run wird erst nach finalem Archiv-Commit und stabiler Beobachtung verarbeitet.
Alte Tage werden nicht nachtraeglich als erfolgreiche Ausfuehrung etikettiert.

Einmaliger, separater Worker-Aufruf nach Freigabe:

```bash
bash "$root/tools/unraid-native-replay-worker.sh" \
  sha256:REVIEWED_64_HEX_IMAGE_ID \
  /mnt/user/appdata/eos-pv-helper/output "$root/replays-v11"
```

Fuer laufenden Betrieb **einen** eigenen User-Scripts-Job mit diesem Aufruf
einrichten, beispielsweise jede Minute oder zeitlich nach dem normalen Dry-Run.
Der bestehende HTML-Job bleibt ein reiner Export. Alternativ den Compose-Dienst
mit explizitem Profil `operator-approved` betreiben; keine beiden Scheduler parallel
einrichten. Compose benoetigt die drei Pfad-/Imagevariablen aus der Vorlage und
startet standardmaessig keinen Dienst. Keine `.env` mit Produktionszugangsdaten.

## Ressourcen, Fortsetzung und Monitoring

- Ein nativer Job gleichzeitig; persistenter flock, vom Kind geerbt.
- 0,5 CPU, CPU-Shares 64, 768 MiB RAM inklusive Swap-Limit, 128 PIDs.
- Private tmpfs: 128 MiB, noexec/nosuid/nodev; keine Core-Dumps.
- Je nativer Prozess: 90 Sekunden Wandzeit, 30 CPU-Sekunden, 3072 MiB virtueller
  Adressraum. Der hoehere Adressraum ist kein zusaetzliches RAM-Kontingent:
  SciPy braucht Platz zum Abbilden seiner Bibliotheken; Docker begrenzt das RAM.
- Nice-Prioritaet mindestens +10. Der Hostaufruf hat einen aeusseren Timeout.
- Ein neuer Scan verarbeitet hoechstens einen Kandidaten. Bei unveraenderten
  erfolgreichen Versionen erfolgen keine nativen Vorwaertslaufe.
- Nur fehlende/in Bearbeitung befindliche Eingaben: maximal drei Versuche,
  Backoff 60/120 Sekunden. Danach `rejected`; keine Endlosschleife.
- Auch wiederholte harte Elternprozessabbrueche ohne vollstaendigen Kandidaten
  sind auf drei gestartete Versuche begrenzt. Ein fertiger Kandidat oder bereits
  veroeffentlichter Sidecar wird dagegen ohne erneute native Rechnung aufgenommen.

`replays-v11/state/status.json` ist ein atomarer privater Status mit `pending`,
`running`, `verified`, `rejected`, `retry_later`, Originalversion/-hash,
EOS-Revision, Dauer, Versuchszahl und festem Fehlercode. CLI-Logs enthalten nur
aggregierte Zustandszaehler oder feste Fehlercodes. Ein Exitcode 0 besagt, dass
der Scan abgeschlossen wurde, nicht dass jeder Kandidat akzeptiert wurde.
`rejected` und ueberfaellige `running`-Eintraege im Monitoring beachten.
`current_jobs` und die CLI-Zaehler beziehen sich auf die jeweils aktuelle
Beobachtung einer Originalversion; fruehere unvollstaendige Beobachtungen bleiben
in `jobs` fuer das Audit erhalten und erzeugen nach einem spaeteren erfolgreichen
Archiv-Commit keinen veralteten Alarm.

`verified/<original-sha256>.json` und `receipts/<original-sha256>.json` sind
unveraenderlich. Receipts binden Original, Archiv, Manifest, Artefakthashes,
Claimhash, Sidecarhash und native Ressourcenmessung. Kandidaten bleiben privat
unter `pending/`, Ablehnungen unter `rejected/`. Nach Abbruch wird ein vollstaendig
gespeicherter Kandidat geprueft weiterverwendet, kein bereits erfolgreicher
Originalhash neu berechnet. Bei kaputten Katalogen/Receipts stoppt Freigabe;
es gibt keinen automatischen Reparatur- oder Loeschmodus.

## Historische Einzelversionen und vorhandene Sidecars

Explizite alte Version ohne Umgehung eines Archiv-/Doctor-Vertrags:

```bash
bash "$root/tools/unraid-native-replay-worker.sh" sha256:REVIEWED_IMAGE_ID \
  /mnt/user/appdata/eos-pv-helper/output "$root/replays-v11" --version ORIGINAL_EVENT_VERSION
```

Die Stabilitaetsbeobachtung erfordert ggf. einen zweiten Aufruf. Eine terminal
abgelehnte Version wird dadurch nicht blind neu gerechnet. Fuer korrigierten
Code eine neue private Review-Generation vorbereiten und vorhandene verifizierte
Sidecars importieren; keine originalen Claims/Archive oder alte Receipts umschreiben.

Der Worker kann mit `--import-sidecar /import/history.json` einen ausdruecklich
ausgewaehlten vorhandenen Sidecar importieren. Dafuer dieselben isolierenden
Docker-Flags verwenden und nur diese eine Datei zusaetzlich read-only nach
`/import/history.json` mounten. Originalbytes muessen eindeutig vorhanden sein;
alle bestehenden nativen Replaypruefungen gelten weiter. Import bedeutet nur
`native_model_reproducibility_only`, niemals historischen Erfolg. Alte Datei
wird nicht geaendert. Mehrere Altplaene und neue automatische Plaene teilen
denselben atomaren, versionierten Katalog.

## HTML-Anbindung nach gesonderter Freigabe

Der Reader aus PR #25/#26 versteht bereits mehrere Plansidecars. Weder Reader,
Exporter noch produktives Helper-Image werden hier geaendert. Neuer Katalog:
`$root/replays-v11/catalog.json`. Vor dem ersten verifizierten Plan fehlt er
absichtlich; unbekannte Fluesse bleiben ohne erfundene Nullwerte.

Der getrennte Adapter `unraid-dashboard-replay-catalog.sh` pinnt beim Oeffnen eine
Kataloggeneration und erstellt eine private Momentaufnahme. Er ruft danach den
unveraenderten Publisher mit dessen bestehendem `--replays` auf. Ein paralleler
Workerwechsel liefert keinen gemischten Transport aus alter Dateilaenge und
neuen Bytes. Bei inhaltlichem Katalogfehler bleibt die letzte gueltige Anzeige
mit ihrem bestehenden Fehlerhinweis erhalten.

Erst nach Abnahme den **Befehl**, nicht den minuetlichen Zeitplan, auf Folgendes
umstellen; vorherige User-Script-Fassung und historischen Sidecarpfad sichern:

```bash
bash "$root/tools/unraid-dashboard-replay-catalog.sh" \
  "$root/tools" "$root/private" "$root/publish" "$root/replays-v11"
```

Adapter und HTML-Refresh starten niemals einen Replay. Der Webserver bekommt
weiterhin nur fertiges HTML. 24h/7d/30d-Zeitbesitz, interne Bruttoenergien,
Wirkungsgrade und EFC-Berechnung bleiben die unveraenderten Readervertraege.

## Private Abnahme und Rollback

1. Gegenreview bestaetigt Hashes, Admission, Ressourcen und Daten-/Socketgrenzen.
2. Vorhandene 29./31.-Sidecars privat importieren und auf Bytegleichheit pruefen.
3. Auf einen **ohnehin regulaeren** neuen Dry-Run warten; keine Suche ausloesen.
4. `pending -> running -> verified` oder konkrete Ablehnung pruefen. Original-/
   Archivhashes unveraendert, genau ein neuer Sidecar, kein zweiter nativer Job.
5. Naechsten normalen HTML-Refresh im LAN pruefen: 24h/7d/30d, keine Doppelzaehlung,
   korrekte Farben/Energiebasis, unbekannte Tage weiter Nicht belegt.
6. Workerabbruch, Neustart und bewusst separate ungueltige Katalogkopie testen;
   letzte gueltige Anzeige bleibt erhalten. Keine produktiven Dateien beschaedigen.

Rollback: ausschliesslich neuen Workerjob deaktivieren bzw. neuen Workercontainer
beenden; HTML-Befehl auf gesicherte v1.0-Fassung mit unveraendertem historischen
Sidecar zurueckstellen. Frequenz, Helper, EOS, evcc, HA, E3/DC, Nginx und Originale
bleiben unveraendert. Neue private Sidecars/Receipts fuer Diagnose behalten.

Grenzen: physische Geraetemessung/Ausfuehrung ist weiterhin nicht bewiesen.
Nicht unterstuetzte EV-/Exportsteuerungen oder Modellparameter werden abgelehnt.
Hashes sind Konsistenznachweise in einer privaten Vertrauensgrenze, keine Signaturen.

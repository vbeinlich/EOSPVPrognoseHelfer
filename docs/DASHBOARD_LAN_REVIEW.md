# EMS Dashboard LAN: PASS / BLOCKED und Gegenreview-Vorlage

Stand 04.11.2026; Grundlage PR #25 / `8011a6d2849f5f17479dd1293f5806d39b3456e7`.
Dies ist der technische Eigenreview samt Nachweisen und vorbereitetem unabhängigem
Abnahmeprotokoll. Ein anderer Reviewer muss seine Prüfung separat bestätigen.
Keine Bereitstellung oder Schedulerfreigabe wird daraus abgeleitet.

| Prüffeld | Status | Nachweis / Grenze |
| --- | --- | --- |
| Bestehender Reader und Wrapper | PASS | Bytegleich zu `DASHBOARD_CODE_HASHES.json`; kein geänderter Helfer |
| Ursache der Replay-Hashabweichung | PASS | Vollständiges Archiv-Writerformat trifft beide Betreiber-SHA-256 exakt; JSON unverändert |
| Direkter Download vom NAS | BLOCKED | SMB-Inhaltsabruf verweigert; keine Rechte geändert; Herkunft der verwendeten hashgleichen Rekonstruktionen explizit dokumentiert |
| Neuer nativer Replay der Betreiber-Bytehashes | PASS | Zwei fixe Vorwärtsläufe je Lösung; kein Optimierer, Forecast oder Baseline; isoliert ohne Netzwerk, nicht root, Originale read-only |
| Neue Sidecar-Bindung | PASS | Unveränderte Exporter-Prüfungen; vollständige Quellbytes, Parameter, EOS-Revision/Fingerprints, Gleichheit und interne Energiebilanzen; keine Hash-Umschreibung |
| Private Originaldaten 29./31.10. im Browser | PASS | Neuer Sidecar trifft Quellbytes; Herkunftssplit, Entladung, SoC, Fenster und interne Zyklen im realen lokalen HTTP-Browser gegen Sidecar geprüft |
| Historischer Erfolg / Modellvorteil | PASS | Einzelantworten bleiben als historisch ungeprüft bezeichnet; kein erfundener erfolgreicher Claim oder Baselinevorteil |
| Originale 30.10. und alle sieben NAS-Archive | BLOCKED | Nicht vollständig lokal übernommen; keine Daten ergänzt; gesamtes NAS-Archiv erst beim privaten Sichttest nachweisen |
| SoC, DST, gestapelte Ladung, fehlende Daten | PASS | Bestehende R24-02/03/04-Tests bleiben; 900-/3600-s-DST-Tests, 1000+1000-Wh-Regression, leere/partielle Historie |
| Historie 24 h / 7 / 30 Tage | PASS | Lokaler HTTP-Browser, auch private Replays; UTC-Überlappungen bleiben ohne Doppelzählung |
| Dark Mode, Desktop, schmale Ansicht | PASS | Edge, 1280/390 Pixel, keine Browserfehler; private Screenshots ausschließlich lokal |
| Nginx-Isolation | PASS | Gepinntes Image, UID/GID 101, rootfs/read-only Mounts, CapDrop ALL, no-new-privileges, Ressourcenlimits; nur fertiges HTML + eigene Nginx-Konfiguration |
| Routen / Geheimnisse | PASS | Nur HTML und leeres favicon; andere Dateien/Pfade 404, POST 405; keine EMS-/Sidecar-/Socket-Mounts, kein Proxy |
| Browser-Netzverkehr | PASS | 0 externe Seitenanfragen in HTTP-Tests; ausschließlich eingebettetes CSS/JS und lokale Seitenanfragen |
| Atomarer HTTP-Dateiaustausch | PASS | Je Test 100 parallele HTTP-Lesezugriffe während Rename: nur vollständige alte/neue HTML-Bytes; Verzeichnismount statt Dateimount |
| Fehlererhalt und Recovery | PASS | Realer Reader über Docker-Transportdouble; ungültige Archive, truncation, Transport- und Codehashfehler; letzte Plandaten und sichtbare Warnung, erfolgreiche Wiederherstellung |
| Schreibschutz gegenüber Output | PASS | Pfadüberschneidungen/Symlinks vor Locks/Publikation abgelehnt; Original-Fingerprints in Tests unverändert |
| Neuer Plan ohne Replay | PASS | Regulärer HTML-Reader zeigt ihn; fehlende Energieflüsse bleiben unbelegt; kein impliziter Replay |
| Automatischer serverseitiger Export | PASS als vorbereitetes Paket | User-Scripts-Vorlage: ausschließlich begrenzter gesperrter HTML-Leseexport; keine Änderung am produktiven Helfer; nicht installiert |
| Port-/Adresskonflikte | PASS lokal, BLOCKED NAS | Read-only Preflight mit IPv4/IPv6-Listener-/Docker-Bindungstests; muss direkt vor tatsächlichem NAS-Start ausgeführt werden |
| Windows und Smartphone auf 192.168.0.186:8505 | BLOCKED | Absichtlich kein Webserver auf Unraid aktiviert; 390-Pixel-Emulation ist kein Smartphone-Heimnetztest |
| Produktive Aktivierung / regelmäßiger Scheduler | BLOCKED | Separate Betreiberfreigabe ausstehend; kein Containerstart, Port oder Scheduler auf Unraid verändert |
| Unabhängiger Gegenreview | BLOCKED | Vorlage bereit; externe Prüfung/Bestätigung steht aus |

## Prüfkommandos

```bash
ruff check src tests scripts
python scripts/update_evidence_transports.py
python scripts/check_dashboard_hashes.py
python scripts/check_dashboard_lan_hashes.py
pytest -q -m 'not genetic_execution'
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7 -shellcheck= -pyflakes=
```

Die bestehende CI behält sämtliche R1/R2/R3- und nativen Sicherheitsprüfungen.
Neu: Publikations-/Preflight-/Archivformat-Regressionen und HTTP-Browser-Smoke mit
neuem synthetischem Archivevent plus 60-s-Reload, sowie native Replay-Ansicht über
den gepinnten Nginx. CI verwendet ausschließlich synthetische Daten; keine privaten
Originale, Sidecars oder Screenshots werden hochgeladen. Optimierungstests bleiben
mit `not genetic_execution` ausgeschlossen. Ergebnisse und finaler Commit sind
im Korrektur-PR und dessen Checks zu vermerken.

Lokal bereits nachgewiesen: vollständiger nativer Lauf **693 bestanden / 3
abgewählt**, einschließlich Archivformat-, Publikations- und Paketbuilder-Tests.
Die finalen CI-Ergebnisse werden zusätzlich im PR angegeben. Unverändertes
Produktionsimage im isolierten Container-Smoke erfolgreich geprüft. Dieser Test
verändert weder den echten Helfer noch seinen Docker-Host.

## Unabhängiger Reviewer: konkret nachprüfen

1. Review-Commit, beide Code-Manifeste, CI und Paketmanifest gegeneinander prüfen.
2. Die beiden Betreiber-Bytehashes auf dem NAS lesend erneut bestätigen; wenn
   möglich zusätzlich tatsächliche Originaldateien privat übernehmen. Dokumentieren,
   ob die hashgeprüfte Rekonstruktion als Erwerbsnachweis akzeptiert wird.
3. Sidecar-Quelldateibindung und native EOS-Fingerprints validieren; kein geänderter
   Hash und kein Ersatz-Forecast. Replay nur isoliert, falls eine erneute Prüfung
   angeordnet wird; Export/Refresh dürfen ihn nicht aufrufen.
4. SoC an Originalintervallanfängen, interne Flüsse/Zyklen und unbekannte Tage
   mit den privaten Daten prüfen. Gespeicherte Freigaben nicht als Energie zählen.
5. Compose/CLI, UID 101, ausschließlich read-only Publikationsmount und eigene
   Konfiguration, genaue LAN-IP sowie Fehlererhalt/Locks gegenprüfen.
6. Stufe A, Stufe B, Webserver und Scheduler getrennt freigeben. Kein Freigabeautomatismus
   aus diesem Bericht, grüner CI oder einem neu erzeugten HTML.

Erster privater Test: einmaliger Stufe-A-Export, nach Betreiberfreigabe nur Nginx
starten, Windows/Smartphone prüfen; dann den hashgeprüften Stufe-B-Sidecar ergänzen.
Erst nach erfolgreichem Sichttest einen weiteren regulären Dry-Run abwarten und
den Scheduler gesondert entscheiden. Anleitung: `DASHBOARD_UNRAID_LAN.md`.

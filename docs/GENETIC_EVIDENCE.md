# Automatische GENETIC-Beweisarchivierung – Issue #12

Review-Implementierung, **nicht auf Unraid installiert oder aktiviert**. Standard
ist `[evidence] enabled = false`. Das Feature startet keine Optimierungen und
ändert weder Preis-/PV-Verarbeitung noch Dispatch-Payload, Zeitplan oder Claims.
Es verarbeitet ausschließlich Erfolge des bereits freigegebenen normalen Syncs.
Die bisherigen historischen Erfolge werden nicht nachträglich vervollständigt.

## Ein Ereignis, sieben Originalartefakte

Ziel: `/output/genetic-evidence/<event-version>.zip`, privat, Dateimodus `0400`,
Verzeichnis `0700`. Inhalt ist genau `snapshot.json` plus:

- `sync-report.json`: ursprünglicher Erfolgsbericht des laufenden Zyklus.
- `sync-state.json`: tatsächlich persistierter erfolgreicher Claim.
- `prices.json`: kanonische, für den Dispatch verwendete Preise.
- `soc.json`: ursprüngliche Messung mit Frische-/Lesebeweis.
- `forecast.json`: ursprüngliche importierte PV-Zeitreihe.
- `report.json`: dazugehöriger PV-Prüfbericht.
- `solution-<event-version>.json`: gespeicherte, validierte Optimierungslösung.

Keine TOML, Env-Dumps, Token-Dateien, evcc-Rohantworten oder zusätzlichen API-
Abrufe. Whitelist, Größenlimits und Privacy-Prüfung stammen aus der eigenständigen
Doctor-Engine von PR #10. ZIPs und Rohdaten sind trotz Inhaltsfilter immer privat.
Die SHA256-Preisversion des vollständigen Liefertags bleibt unverändert.

## Reihenfolge und Konsistenz

1. Der vollständige Zyklus hält wie bisher `sync.lock` exklusiv. Vor dem POST
   werden die vier Eingabedateien in unveränderten Bytes festgehalten. Preise
   müssen dem tatsächlich verwendeten Frame entsprechen, SoC und PV-Bericht den
   Zyklusvariablen. PV-Werte müssen in jedem 15-Minuten-Intervall des Control-/Tail-
   Fensters mit der bereits gelesenen EOS-Serie übereinstimmen. Danach gelten die
   bestehenden finalen SoC-Frische- und Slot-Prüfungen weiterhin.
2. Der persistierte Claim bleibt vor dem POST **uncertain**. Erst die bestätigte
   und validierte Antwort erlaubt wie bisher Lösungsdatei und `succeeded`.
3. Der originale erfolgreiche State und Report werden wie bisher atomar und
   dauerhaft geschrieben. Erst anschließend werden diese Originalbytes und die
   Lösung mit den vorher festgehaltenen Eingaben verbunden und vollständig durch
   den historischen Doctor validiert. Dateien nach dem POST sind kein Ersatz für
   die festgehaltenen Dispatch-Eingaben.
4. Ein vollständiges ZIP wird privat vorbereitet, `fsync`-gesichert und mit einem
   exklusiven Hardlink als `.pending/<version>.ready` bereitgestellt. Ein weiterer
   exklusiver Hardlink veröffentlicht `<version>.zip` atomar ohne Überschreiben.
   Verzeichnis- und Dateidaten werden synchronisiert. Eine separate Archive-Lock-
   Datei verhindert konkurrierende Publikationen; Lockreihenfolge ist immer
   `sync.lock` vor `archive.lock`.
5. Erst nach Veröffentlichung erhält der aktuelle Report `evidence.status=archived`,
   relativen Pfad und ZIP-SHA256. Dieser zweite Report-Schreibvorgang ergänzt nur
   den Archivierungsstatus. Der **archivierte** Originalreport stammt aus Schritt 3,
   ohne selbstreferenziellen ZIP-Hash. Claims und Archivbytes werden nicht geändert.

## Schema 2 und Provenienz

Unverändertes Doctor-Historien-Schema 2: sieben Artefaktnamen, ihre SHA256-Hashes,
Event-Version, echte Erhebungszeit, Zeitzone und konfigurierte Prüfgrenzen.
Die Engine aus PR #10 wird bytegleich wiederverwendet, keine abweichende Kopie:
SHA256 ohne Schluss-Zeilenumbruch
`d4d713cd53c3a94621032ea7aeb2c76b5787b96e53ec8658544ab248c896a564`.

Dokumentierte **optionale** Manifest-Erweiterung `producer` (kein Schemawechsel):
`contract=eos-pv-helper/automatic-evidence-v1`, `input_captured_at_utc`, ursprüngliches
`claimed_at_utc`, `implementation_sha256` des installierten Archivierungsmoduls und
`doctor_engine_sha256`. Der Producer prüft Eingangserhebung ≤ Claim ≤ Erhebung des
fertigen Nachweises. Vorhandene Schema-2-Leser erlauben dieses Metadatenobjekt und
prüfen weiterhin alle sieben Originalartefakte. Sie authentifizieren diese
zusätzlichen Herkunftsangaben nicht unabhängig; Herkunft bleibt Betreiberreview.

SoC-Frische wird historisch am unveränderten Claim-Zeitpunkt geprüft, höchstens
300 s oder strengere Grenze, Leseabschluss vor Dispatch. Preisversion, vollständige
Preis-/PV-Zeitachsen und Control-/Tail-Abdeckung müssen passen. Ausgabe:
`evidence_mode=historical_snapshot`, `historical_reference_kind=persisted_claim`,
`current_freshness_verified=false`. Keine rekonstruierten Werte oder Zeitstempel.

## Fehler, Neustarts und Unveränderlichkeit

- Ohne Opt-in bzw. im Dry-run keine neuen Archivdateien und keine Recovery-Schreibzugriffe.
- `waiting-publication` erzeugt kein neues Archiv. Vorhandene ZIPs bleiben unverändert.
- Gleiche Event-Version: kein weiterer POST, keine erneute Archivierung mit neueren
  Eingaben. Ein vorhandenes gültiges Archiv wird nur geprüft. Fehlendes altes Archiv
  meldet `evidence_missing`, auch wenn heutige Dateien vollständig erscheinen.
- Archivefehler ändern den bestätigten Optimierungserfolg nicht. Report und Health
  zeigen den fehlenden Nachweis; es gibt keinen automatischen Optimierer-Retry.
- Nach einem Abbruch darf ausschließlich eine **vollständige, bereits gespeicherte**
  `.ready`-Datei wiederaufgenommen werden. Sie muss mit dem persistierten erfolgreichen
  Claim und den Lösungsbytes übereinstimmen. Neuere Preise/Reports werden nicht verwendet.
- Crash zwischen Claim, Lösung, State/Report und vollständiger Ready-Datei kann einen
  fehlenden Nachweis hinterlassen. Dieser wird ausdrücklich gemeldet und **nicht**
  rekonstruiert. Uncertain-Claims bleiben uncertain. Für eine lückenlose Transaktion
  über Optimierer und Dateisystem wäre eine Änderung des bestehenden Protokolls nötig;
  diese Implementierung behauptet eine solche Garantie nicht.
- Beschädigte ZIPs, unerwartete Symlinks, inkompatible Dateisysteme, unvollständige
  Eingaben oder Privacy-Verstöße führen zu Diagnose statt Überschreiben/Reparatur.
- Die Anwendung ersetzt und löscht keine finalen Archive. `0400`, Hashes und exklusive
  Publikation schützen gegen Anwendungsfehler, sind aber kein WORM-Speicher und keine
  Signatur gegen privilegierte externe Manipulation.
- Entfernt werden nur eigene temporäre Dateien und nach erfolgreichem Commit die
  zusätzliche Staging-Verknüpfung. Unbekannte/verwaiste Dateien nicht automatisch löschen.

Der Live-Doctor verlangt bei `[evidence] enabled=true` zusätzlich das vollständige
gültige Event-Archiv. Ein bloßes `evidence.status=archived` im Report reicht nicht.
Der historische Doctor akzeptiert nur vollständig validierte Eingaben. Alte
Vier-Artefakt-Snapshots sind für diese Abnahme unvollständig; die GENETIC-Abnahme
aus Issue #1 und bestehende Claims bleiben unangetastet.

## Speicherplatz und Aufbewahrung

Keine automatische Retention-Löschung. Ein neues Archiv benötigt seinen ZIP-Platz
zuzüglich mindestens 1 MiB Reserve; tatsächliche I/O-/fsync-Fehler werden trotzdem
behandelt. Die atomaren Verknüpfungen müssen auf demselben Dateisystem liegen.
Obergrenzen: 8 MB je Rohartefakt und 60 MB je ZIP. Privat sichern und freien Platz
überwachen; keine unbegrenzte Verfügbarkeit behaupten. Bereinigung, Retention und
zusätzliche Backups sind gesonderte Betreiberentscheidungen. Kein Upload zu GitHub.

## Migration und spätere Unraid-Abnahme – nur nach Freigabe

1. Separaten PR prüfen; nicht automatisch mergen. Dieses Feature ist noch nicht im
   unveränderten produktiven Image und nicht im eingefrorenen Kandidaten enthalten.
2. Neues Image mit dieser Quellrevision benötigt eigene Build-/Hash-/Lizenz-/Release-
   Prüfung und ausdrücklich freigegebenes Deployment. Alte Digest-Freigaben nicht
   auf einen Neubau übertragen. Dieser Auftrag führt keine dieser Aktionen durch.
3. Erst danach optional `[evidence] enabled = true` in der privaten Konfiguration
   setzen. Bestehende SoC-/PV-/Preis-/Trigger-Freigaben und Parameter nicht ändern.
   Persistentes vorhandenes Output-Volume verwenden; keine zweite Instanz starten.
4. Den **nächsten ohnehin regulären** erfolgreichen GENETIC-Lauf abwarten. Kein
   manueller POST, kein Claim-Reset und keine Backfill-Optimierung.
5. Relativen Archivpfad/SHA256 aus `sync-report.json.evidence` privat notieren.
   Pfad stammt aus dem tatsächlichen Output-Bind-Mount, nicht aus erfundenen NAS-Pfaden.
6. Mit dem bereits geprüften eigenständigen Wrapper aus PR #10 und dessen bekannten
   Hash rein lesend prüfen; `VERSION`/`EXISTING_HOST_OUTPUT` durch echte Werte ersetzen:

   ```sh
   sha256sum /EXISTING_HOST_OUTPUT/genetic-evidence/VERSION.zip
   bash /PRIVATE/unraid-doctor-export-reviewed.sh --check-only \
     --historical-snapshot /EXISTING_HOST_OUTPUT/genetic-evidence/VERSION.zip \
     --event-version VERSION
   ```

   Der optionale spätere private `--export` verwendet dieselben Optionen und
   übernimmt die vorhandenen ZIP-Bytes unverändert. Export bleibt gesonderte
   Operatoraktion, hier nicht auf Unraid ausgeführt.
7. Auch nach späterem `waiting-publication` muss dieser Vorabtest funktionieren.
   Offline die kopierte ZIP mit der eigenständigen Engine oder dem neuen Diagnose-
   Checkout prüfen: `python -B -m eos_pv_helper doctor --snapshot PRIVATE.zip`.
   Im alten Container die separat geprüfte Engine mit `python -I -S -B` verwenden;
   dort kein eingebautes Schema-2-Modul voraussetzen. Keine Live-Verzeichnisse/Sockets
   auf dem Diagnose-Rechner mounten. Hashes und Herkunft privat bestätigen lassen.

## Tests und Kompatibilität

Neue Optimierungsantworten in den Archivtests sind ausschließlich gemockt. Tests
decken Erfolg, spätere Waiting-Reports, verschiedene Preisversionen, DST, Neustarts
an mehreren Persistenzgrenzen, parallele Writer, fehlende/vertauschte Eingaben,
Privacy, knappen Speicher, I/O-Fehler und spätere historische Abnahme ab. Ein
Vergleich der vollständigen HTTP-Aufrufe/Payloads belegt: keine zusätzlichen Abrufe
und keine geänderte Optimierungsanfrage. Eingabe-I/O kann die finale SoC-Frische-
prüfung nicht umgehen.

Realer Container-Kompatibilitätstest mit **vom neuen Writer erzeugter synthetischer
ZIP**, nicht nur manuell gebautem Manifest: je fünf Szenarien im Produktions-Digest
`7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7` (kein `doctor.py`)
und im eingefrorenen OCI-Kandidaten `69d4e1974bb5190d6fd63b2533c5e1c71e23589dd1e1314c6744659dcbded61a`.
Keine Projektquellcode-Mounts in diesen Consumern, Pakete mit `-I -S` nicht
importierbar, Non-root/read-only, Netzwerk aus. Herkunft des lokalen Kandidaten
über OCI-/Config-/RootFS-/Inventar-/Quellenbindung erneut erfolgreich geprüft.
Die alten Images können diese Nachweise mit der eigenständigen Engine lesen;
sie erhalten dadurch **keine** automatische Schreibfunktion.

Reproduktion auf lokalem Linux-Entwicklungsrechner mit Testabhängigkeiten:

```sh
pytest -q -m 'not genetic_execution'
python tests/make_evidence_fixture.py --destination /PRIVATE/NEW-SYNTHETIC-FIXTURE
python scripts/evidence_container_smoke.py --docker-context LOCAL_DEVELOPMENT \
  --image ghcr.io/vbeinlich/eospvprognosehelfer@sha256:7e957da3e2fdb67456a46e5538ad3c74b43fa21892d2998e93bca9de83d9daf7 \
  --fixture /PRIVATE/NEW-SYNTHETIC-FIXTURE --expect-no-doctor
```

Die CI zieht nur diesen bereits öffentlichen unveränderlichen Digest zur Prüfung,
veröffentlicht selbst kein Image und lädt keine privaten Archive hoch.

**Prüfabweichung:** Beim ersten lokalen Gesamtlauf auf der unabhängigen Main-Basis
fehlten die drei Testmarkierungen noch. Deshalb wurden unbeabsichtigt drei lokale
synthetische GENETIC-Tests im netzwerkisolierten Wegwerfcontainer ausgeführt, ohne
Produktionszugriff. Markierungen, CI-Auswahl und eine AST-Prüfung sind korrigiert;
der abschließende Review-/CI-Lauf schließt diese drei Tests explizit aus. Diese
synthetischen Ergebnisse werden nicht als reale Abnahme oder Freigabe verwendet.

Offen bleiben unabhängiger Review, etwaige spätere Deployment-/Aktivierungsfreigabe
und die tatsächliche private Abnahme am nächsten regulären Ereignis. Issue #12
nicht wegen synthetischer Tests als produktiv abgenommen schließen.

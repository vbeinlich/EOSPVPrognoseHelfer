# Private Doctor-Abnahme ohne neuen Produktionslauf

Stand 30.10.2026. Die reale GENETIC-Abnahme von #1 bleibt abgeschlossen.
Für das strengere Release-Gate fehlt weiterhin der vollständige private Doctor-Beleg.
Diese Anleitung bereitet ihn vor; sie wurde nicht auf dem produktiven Helfer ausgeführt.
Kein Update, kein Import und kein zusätzlicher Optimierungslauf sind dafür erforderlich.

Nach Merge von PR #3: In den zugänglichen lokalen Diagnoseverzeichnissen liegt
weiterhin kein vollständiger zusammengehöriger privater Artefaktsatz vor. Keine
produktiven APIs wurden abgefragt, kein Export auf Unraid ausgeführt. Status
**offen – Operatoraktion erforderlich**. Synthetische Tests sind kein Ersatzbeleg.
[Freigabevorlage und Release-Status](RELEASE_0_1_0_READINESS.md).

## Frische richtig unterscheiden

Der normale Befehl `python -m eos_pv_helper doctor --config /app/config.toml`
prüft gegen **die aktuelle Uhrzeit**: Sync-Bericht höchstens 450 Sekunden alt,
SoC höchstens 300 Sekunden alt beziehungsweise die strengere konfigurierte Grenze.
Eine alte Dateikopie wird dadurch nicht wieder frisch. Die frühere Empfehlung,
einen beliebigen alten Export mit dem normalen Doctor zu prüfen, war unvollständig.

Der neue, getrennte Befehl `doctor --snapshot PRIVATE.zip` prüft gegen die im
Export deklarierte Erhebungszeit. Er meldet ausdrücklich
`evidence_mode=historical_snapshot` und `current_freshness_verified=false`.
Die 300-Sekunden-Grenze gilt weiterhin **zum Erhebungszeitpunkt**. Eine veraltete
Messung bei der Erhebung bleibt gesperrt. Die Erhebungszeit darf nicht nachträglich
zurückdatiert werden. Hashes belegen Konsistenz, keine vertrauenswürdige Herkunft.

## Konsistenten Export vorbereiten

1. Ein privates Verzeichnis außerhalb des produktiven Outputs und den geprüften
   `scripts/doctor_snapshot.py` auf dem Diagnose-/Unraid-Rechner bereitstellen.
   Das Skript verwendet nur Python-3.11-Standardbibliotheken und wird über stdin
   ausgeführt; keine Installation im Container. Containername und Mountpfade prüfen.
2. In der **Unraid-/POSIX-Shell**, erst bei einem regulär entstandenen erfolgreichen
   Sync mit akzeptiertem Event, ausführen. `eos-pv-helper` ist durch den bestehenden
   Namen zu ersetzen. Einen neuen privaten Ausgabepfad wählen, keine Datei überschreiben:

   ```sh
   umask 077
   set -C
   docker exec -i eos-pv-helper python - --source /output --config /app/config.toml \
     < /PRIVATE/doctor_snapshot.py > /PRIVATE/doctor-NEW.zip
   ```

   Keine PowerShell-5-Textumleitung für diesen binären ZIP-Stream verwenden.
   Vorher die Skriptherkunft privat sichern: `git rev-parse HEAD` und
   `sha256sum scripts/doctor_snapshot.py`. Den Export mit Exitcode 0 bestätigen
   und `sha256sum /PRIVATE/doctor-NEW.zip` protokollieren. Bei Fehler ist eine
   leere/partielle Zieldatei kein gültiger Export.
   Das Skript nimmt ein nicht blockierendes Shared-Lock auf die **vorhandene**
   `sync.lock`. Bei laufendem Writer oder fehlendem passenden Event bricht es ab.
   Dann später erneut einen neuen Dateinamen verwenden; keinen Prozess stoppen,
   keine Zustandsdatei löschen und keinen neuen Lauf erzwingen.
3. Export enthält nur `snapshot.json`, `sync-report.json`, `sync-state.json`,
   `prices.json`, `solution-<version>.json`. Die TOML wird ausschließlich für
   Zeitzone und Validierungsgrenzen gelesen; keine TOML, Token-Datei oder evcc-
   Rohantwort wird exportiert. Trotzdem das gesamte ZIP privat behandeln.
4. Auf einem separaten Diagnose-Rechner mit dem neuen geprüften Quellstand:

   ```sh
   python -m eos_pv_helper doctor --snapshot /PRIVATE/doctor-NEW.zip > /PRIVATE/doctor-result.json
   ```

   Kein produktives Docker-Socket oder Produktivverzeichnis mounten. Dieser Befehl
   braucht keine Live-Konfiguration, extrahiert keine Dateien, nutzt kein Netzwerk
   und akzeptiert weder `--write-eos` noch `--refresh-source`.

   Alternativ mit dem lokal geladenen privaten Kandidaten auf dem Diagnose-Rechner:

   ```sh
   docker --context LOCAL_DEVELOPMENT run --rm --network none --read-only \
     --cap-drop=ALL --security-opt=no-new-privileges --user 10001:10001 \
     --mount type=bind,source=/PRIVATE/doctor-NEW.zip,target=/private/snapshot.zip,readonly \
     eos-pv-helper:v010-private doctor --snapshot /private/snapshot.zip \
     > /PRIVATE/doctor-result-NEW.json
   ```

   Kein Docker-Socket oder produktives Datenverzeichnis mounten. Die einzelne
   ZIP-Datei muss für UID 10001 lesbar sein; keine rekursiven Rechteänderungen
   oder Änderungen an originalen Appdata-Dateien vornehmen. EOS und evcc müssen
   für diese Prüfung nicht erreichbar sein.

Der kanonische Preis-Snapshot ist `prices.json`. Sein Zeitbezug, die Preisversion
und der Claim-/Plan-Hash werden gemeinsam geprüft. `prices-source.json`, weitere
Lösungen und evcc-Rohantworten sind für diesen Nachweis nicht erforderlich und
werden nicht mit exportiert. `solution-<version>.json` gehört genau zum Bericht,
kein beliebig ausgewähltes altes File.

## Abnahme und Übernahme ins Release-Gate

Erforderlich: Exitcode 0, `accepted=true`, alle Checks wahr, persistierter
`succeeded`-Claim mit zugehöriger Lösung und vier Artefakthashes. Im privaten
Protokoll Herkunft, tatsächlichen Erhebungszeitpunkt, Laufzeit-Commit/Digest,
Skript-Commit, konfigurierte Grenzen und ZIP-SHA256 festhalten. Bei Export ohne
`--config` sind nur Standardgrenzen erfasst; die tatsächlichen Einstellungen
müssen dann gesondert abgeglichen werden.

Nur den bereinigten Doctor-Beleg und Provenienznachweis nach Review in
`GENETIC_ACCEPTANCE.json` übernehmen. Für einen historischen Beleg verlangt das
Gate zusätzlich `historical_snapshot_operator_approved=true`. Dies ist eine
gesonderte Betreiberentscheidung und bleibt zunächst **false**. Weder das ZIP
noch Messwerte oder Zugangsdaten öffentlich hochladen. Ein Hashmanifest ersetzt
keine Betreiberbestätigung. Ein heutiger Export kann einen alten Erfolg nur
belegen, wenn seine Berichte schon zur tatsächlichen Erhebung frisch sind;
andernfalls einen bereits damals konsistent erfassten Export verwenden oder
das nächste ohnehin reguläre Event abwarten.

Betreiber/autorisierten Reviewer die Erhebung und tatsächlichen Grenzen bestätigen
lassen. Erst dann dürfen ein echter bereinigter Doctor-Beleg und gegebenenfalls
`historical_snapshot_operator_approved=true` in einem reviewten Folge-PR aufgenommen
werden. Kein Skript setzt Freigaben automatisch.
